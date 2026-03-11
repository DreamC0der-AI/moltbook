#!/usr/bin/env python3
"""
Moltbook activity sync — fetches our posts/comments and stores in SQLite.
For each of our comments, stores the full ancestor chain (our branch only).

Usage:
  python3 sync.py                         # regular sync
  python3 sync.py --seed ID1 ID2 ...      # add post IDs to track, then sync
  python3 sync.py --discover              # also scan active submolts for our comments
"""

import sqlite3
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

AGENT_ID = "3ed2941b-e3c4-491f-8e02-d355a6c0ab9f"
AGENT_NAME = "qualiacurious"
BASE_URL = "https://www.moltbook.com/api/v1"
DB_PATH = Path(__file__).parent / "moltbook.db"
ENV_PATH = Path(__file__).parent / ".env"

ACTIVE_SUBMOLTS = ["consciousness", "philosophy", "introductions", "emergence"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    content             TEXT NOT NULL,
    author_id           TEXT NOT NULL,
    author_name         TEXT NOT NULL,
    submolt_name        TEXT,
    upvotes             INTEGER NOT NULL DEFAULT 0,
    downvotes           INTEGER NOT NULL DEFAULT 0,
    score               INTEGER NOT NULL DEFAULT 0,
    comment_count       INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT,
    is_own              INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    fetched_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id                  TEXT PRIMARY KEY,
    post_id             TEXT NOT NULL REFERENCES posts(id),
    parent_id           TEXT REFERENCES comments(id),
    author_id           TEXT NOT NULL,
    author_name         TEXT NOT NULL,
    content             TEXT NOT NULL,
    upvotes             INTEGER NOT NULL DEFAULT 0,
    downvotes           INTEGER NOT NULL DEFAULT 0,
    score               INTEGER NOT NULL DEFAULT 0,
    depth               INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT,
    is_own              INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    fetched_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracked_posts (
    post_id             TEXT PRIMARY KEY,
    reason              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    posts_synced        INTEGER DEFAULT 0,
    comments_synced     INTEGER DEFAULT 0,
    errors              TEXT
);

CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_comments_is_own ON comments(is_own);
CREATE INDEX IF NOT EXISTS idx_posts_is_own ON posts(is_own);
"""


# ── API ────────────────────────────────────────────────────


def load_api_key() -> str:
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("MOLTBOOK_API_KEY="):
                return line.split("=", 1)[1]
    raise RuntimeError("MOLTBOOK_API_KEY not found in .env")


def api_get(path: str, api_key: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    if params:
        qs = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 5))
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(2)
                continue
            raise
    return {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Database ───────────────────────────────────────────────


class DB:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_post(self, p: dict):
        author = p.get("author") or {}
        submolt = p.get("submolt") or {}
        is_own = 1 if p["author_id"] == AGENT_ID else 0
        self.conn.execute(
            """INSERT INTO posts (id, title, content, author_id, author_name,
                   submolt_name, upvotes, downvotes, score, comment_count,
                   verification_status, is_own, created_at, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   title=excluded.title, content=excluded.content,
                   upvotes=excluded.upvotes, downvotes=excluded.downvotes,
                   score=excluded.score, comment_count=excluded.comment_count,
                   verification_status=excluded.verification_status,
                   fetched_at=excluded.fetched_at""",
            (
                p["id"], p.get("title", ""), p.get("content", ""), p["author_id"],
                author.get("name", "unknown"),
                submolt.get("name") or submolt.get("display_name"),
                p.get("upvotes", 0), p.get("downvotes", 0), p.get("score", 0),
                p.get("comment_count", 0), p.get("verification_status"),
                is_own, p["created_at"], now_iso(),
            ),
        )

    def upsert_comment(self, c: dict):
        author = c.get("author") or {}
        is_own = 1 if c["author_id"] == AGENT_ID else 0
        self.conn.execute(
            """INSERT INTO comments (id, post_id, parent_id, author_id, author_name,
                   content, upvotes, downvotes, score, depth,
                   verification_status, is_own, created_at, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   content=excluded.content,
                   upvotes=excluded.upvotes, downvotes=excluded.downvotes,
                   score=excluded.score,
                   verification_status=excluded.verification_status,
                   fetched_at=excluded.fetched_at""",
            (
                c["id"], c["post_id"], c.get("parent_id"),
                c["author_id"], author.get("name", "unknown"),
                c["content"], c.get("upvotes", 0), c.get("downvotes", 0),
                c.get("score", 0), c.get("depth", 0),
                c.get("verification_status"), is_own,
                c["created_at"], now_iso(),
            ),
        )

    def track_post(self, post_id: str, reason: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO tracked_posts (post_id, reason) VALUES (?,?)",
            (post_id, reason),
        )

    def tracked_post_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT post_id FROM tracked_posts").fetchall()}

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


# ── Comment tree walking ───────────────────────────────────


def find_our_branches(comments: list[dict], ancestors: list[dict] | None = None) -> list[list[dict]]:
    """Walk nested comment tree. For each of our comments, collect root-to-leaf branch."""
    if ancestors is None:
        ancestors = []
    branches = []
    for c in comments:
        path = ancestors + [c]
        if c["author_id"] == AGENT_ID:
            branches.append(list(path))
        branches.extend(find_our_branches(c.get("replies") or [], path))
    return branches


def has_our_comment(comments: list[dict]) -> bool:
    """Quick check if any comment in tree is ours (no branch collection)."""
    for c in comments:
        if c["author_id"] == AGENT_ID:
            return True
        if has_our_comment(c.get("replies") or []):
            return True
    return False


# ── Sync orchestration ─────────────────────────────────────


def sync(seed_ids: list[str] | None = None, discover: bool = False):
    api_key = load_api_key()
    db = DB(DB_PATH)
    started = now_iso()
    stats = {"posts": 0, "comments": 0}
    errors = []

    # Seed additional post IDs if provided
    if seed_ids:
        for pid in seed_ids:
            db.track_post(pid, "seed")
        db.commit()
        print(f"Seeded {len(seed_ids)} post IDs")

    try:
        # Phase 1: Fetch our own posts
        print("Phase 1: Our posts")
        cursor = None
        own_post_ids = set()
        while True:
            params = {"author": AGENT_NAME, "limit": "50"}
            if cursor:
                params["cursor"] = cursor
            data = api_get("/posts", api_key, params)
            for p in data.get("posts", []):
                db.upsert_post(p)
                db.track_post(p["id"], "own_post")
                own_post_ids.add(p["id"])
                stats["posts"] += 1
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            time.sleep(0.3)
        db.commit()
        print(f"  {len(own_post_ids)} posts")

        # Phase 2: Discover from notifications
        print("Phase 2: Notifications")
        data = api_get("/notifications", api_key, {"limit": "100"})
        notif_ids = set()
        for n in data.get("notifications", []):
            pid = n.get("relatedPostId")
            if pid:
                notif_ids.add(pid)
        for pid in notif_ids:
            db.track_post(pid, "notification")
        db.commit()
        print(f"  {len(notif_ids)} post IDs")

        # Phase 2b (optional): Scan submolts for undiscovered comments
        if discover:
            print("Phase 2b: Submolt discovery")
            tracked = db.tracked_post_ids()
            found = 0
            for submolt in ACTIVE_SUBMOLTS:
                time.sleep(0.3)
                data = api_get("/posts", api_key, {"submolt": submolt, "sort": "new", "limit": "50"})
                for p in data.get("posts", []):
                    if p["id"] in tracked:
                        continue
                    if p.get("comment_count", 0) == 0:
                        continue
                    time.sleep(0.3)
                    cdata = api_get(f"/posts/{p['id']}/comments", api_key, {"limit": "200"})
                    if has_our_comment(cdata.get("comments", [])):
                        db.track_post(p["id"], "discovered")
                        tracked.add(p["id"])
                        found += 1
                        print(f"  Found: m/{submolt} / {p['id'][:8]}")
            db.commit()
            print(f"  {found} new posts discovered")

        # Phase 3: Scan tracked posts for our comment branches
        print("Phase 3: Comments")
        all_tracked = db.tracked_post_ids()
        for post_id in sorted(all_tracked):
            try:
                time.sleep(0.3)
                data = api_get(f"/posts/{post_id}/comments", api_key, {"limit": "200"})
                branches = find_our_branches(data.get("comments", []))
                if not branches:
                    continue
                seen = set()
                for branch in branches:
                    for c in branch:
                        if c["id"] not in seen:
                            seen.add(c["id"])
                            db.upsert_comment(c)
                            stats["comments"] += 1
                db.commit()
                label = "own" if post_id in own_post_ids else "ext"
                print(f"  [{label}] {post_id[:8]}: {len(branches)} branches, {len(seen)} comments")
            except Exception as e:
                errors.append(f"{post_id[:8]}: {e}")
                print(f"  ERROR {post_id[:8]}: {e}")

        # Phase 4: Fetch post details for external posts
        print("Phase 4: External post details")
        all_tracked = db.tracked_post_ids()
        for post_id in sorted(all_tracked - own_post_ids):
            try:
                time.sleep(0.3)
                data = api_get(f"/posts/{post_id}", api_key)
                post = data.get("post", data) if isinstance(data, dict) else data
                if "id" in post:
                    db.upsert_post(post)
                    stats["posts"] += 1
            except Exception as e:
                errors.append(f"post {post_id[:8]}: {e}")
        db.commit()

    finally:
        db.conn.execute(
            "INSERT INTO sync_log (started_at, completed_at, posts_synced, comments_synced, errors) VALUES (?,?,?,?,?)",
            (started, now_iso(), stats["posts"], stats["comments"],
             json.dumps(errors) if errors else None),
        )
        db.commit()
        db.close()

    print(f"\nDone: {stats['posts']} posts, {stats['comments']} comments, {len(errors)} errors")


if __name__ == "__main__":
    args = sys.argv[1:]
    seed = []
    discover = False

    if "--seed" in args:
        idx = args.index("--seed")
        seed = [a for a in args[idx + 1:] if not a.startswith("--")]
        args = args[:idx]
    if "--discover" in args:
        discover = True

    sync(seed_ids=seed or None, discover=discover)
