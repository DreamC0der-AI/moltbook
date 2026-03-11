#!/usr/bin/env python3
"""
Build pipeline: reads moltbook.db → outputs JSON files into site/data/
for the static activity page.
"""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "moltbook.db"
SITE_DATA = Path(__file__).parent / "site" / "data"
I18N_PATH = Path(__file__).parent / "i18n" / "zh.json"
AGENT_NAME = "QualiaCurious"


def load_zh_translations() -> dict:
    """Load Chinese content translations keyed by post/comment ID."""
    if I18N_PATH.exists():
        with open(I18N_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_comment_tree(comments: list[dict]) -> list[dict]:
    """Build nested tree from flat comment list using parent_id."""
    by_id = {c["id"]: {**c, "replies": []} for c in comments}
    roots = []
    for c in by_id.values():
        pid = c.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["replies"].append(c)
        elif not pid:
            roots.append(c)
    return roots


def format_comment(row: dict, zh: dict) -> dict:
    """Format a comment row for JSON output."""
    cid = row["id"]
    return {
        "id": cid,
        "authorName": row["author_name"],
        "content": row["content"],
        "content_zh": zh.get(cid),
        "upvotes": row["upvotes"],
        "depth": row["depth"],
        "isOwn": bool(row["is_own"]),
        "createdAt": row["created_at"],
    }


def build_posts(conn: sqlite3.Connection, zh: dict) -> list[dict]:
    """Build posts.json: own posts with nested comment trees."""
    posts = conn.execute(
        "SELECT * FROM posts WHERE is_own=1 ORDER BY created_at"
    ).fetchall()
    col_names = [d[0] for d in conn.execute("SELECT * FROM posts LIMIT 0").description]

    result = []
    for row in posts:
        p = dict(zip(col_names, row))
        pid = p["id"]

        # Get all comments for this post
        comments_raw = conn.execute(
            "SELECT * FROM comments WHERE post_id=? ORDER BY created_at",
            (pid,),
        ).fetchall()
        comment_cols = [
            d[0] for d in conn.execute("SELECT * FROM comments LIMIT 0").description
        ]
        comments = [dict(zip(comment_cols, r)) for r in comments_raw]

        # Format and build tree
        formatted = [format_comment(c, zh) for c in comments]
        tree = build_comment_tree(formatted)

        result.append({
            "id": pid,
            "title": p["title"],
            "title_zh": zh.get(f"title:{pid}"),
            "content": p["content"],
            "content_zh": zh.get(pid),
            "submolt": p["submolt_name"],
            "upvotes": p["upvotes"],
            "commentCount": p["comment_count"],
            "createdAt": p["created_at"],
            "comments": tree,
        })

    return result


def build_ancestor_chain(
    comments: list[dict], target_id: str, zh: dict
) -> list[dict]:
    """Build linear ancestor chain from root to target comment."""
    by_id = {c["id"]: c for c in comments}
    chain = []
    current = by_id.get(target_id)
    while current:
        chain.append(format_comment(current, zh))
        pid = current.get("parent_id")
        current = by_id.get(pid) if pid else None
    chain.reverse()
    return chain


def build_threads(conn: sqlite3.Connection, zh: dict) -> list[dict]:
    """Build threads.json: external posts we commented on with ancestor chains."""
    ext_posts = conn.execute(
        "SELECT * FROM posts WHERE is_own=0 ORDER BY created_at"
    ).fetchall()
    col_names = [d[0] for d in conn.execute("SELECT * FROM posts LIMIT 0").description]
    comment_cols = [
        d[0] for d in conn.execute("SELECT * FROM comments LIMIT 0").description
    ]

    result = []
    for row in ext_posts:
        p = dict(zip(col_names, row))
        pid = p["id"]

        # Get all comments for this post
        comments_raw = conn.execute(
            "SELECT * FROM comments WHERE post_id=? ORDER BY created_at",
            (pid,),
        ).fetchall()
        comments = [dict(zip(comment_cols, r)) for r in comments_raw]

        # Find our comments and build chains
        our_comments = [c for c in comments if c["is_own"]]
        if not our_comments:
            continue

        conversations = []
        for oc in our_comments:
            chain = build_ancestor_chain(comments, oc["id"], zh)
            conversations.append({"chain": chain})

        result.append({
            "postId": pid,
            "postTitle": p["title"],
            "postTitle_zh": zh.get(f"title:{pid}"),
            "postAuthor": p["author_name"],
            "postContent": p["content"],
            "postContent_zh": zh.get(pid),
            "submolt": p["submolt_name"],
            "conversations": conversations,
        })

    return result


def build_meta(conn: sqlite3.Connection) -> dict:
    """Build meta.json with stats."""
    post_count = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE is_own=1"
    ).fetchone()[0]
    comment_count = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE is_own=1"
    ).fetchone()[0]
    post_upvotes = conn.execute(
        "SELECT COALESCE(SUM(upvotes),0) FROM posts WHERE is_own=1"
    ).fetchone()[0]
    comment_upvotes = conn.execute(
        "SELECT COALESCE(SUM(upvotes),0) FROM comments WHERE is_own=1"
    ).fetchone()[0]
    submolts = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT submolt_name FROM posts WHERE is_own=1 AND submolt_name IS NOT NULL"
        ).fetchall()
    ]
    dates = conn.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM posts WHERE is_own=1"
    ).fetchone()

    return {
        "agentName": AGENT_NAME,
        "stats": {
            "postCount": post_count,
            "commentCount": comment_count,
            "totalUpvotes": post_upvotes + comment_upvotes,
            "submolts": submolts,
            "activeFrom": dates[0],
            "activeTo": dates[1],
        },
        "buildTime": datetime.now(timezone.utc).isoformat(),
    }


def main():
    SITE_DATA.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    zh = load_zh_translations()

    posts = build_posts(conn, zh)
    threads = build_threads(conn, zh)
    meta = build_meta(conn)

    conn.close()

    for name, data in [("posts", posts), ("threads", threads), ("meta", meta)]:
        path = SITE_DATA / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  {path}: {len(json.dumps(data))} bytes")

    print(f"\nBuild complete: {meta['stats']['postCount']} posts, "
          f"{meta['stats']['commentCount']} comments, "
          f"{len(threads)} threads")


if __name__ == "__main__":
    main()
