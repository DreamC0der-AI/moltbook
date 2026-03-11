/**
 * Render module — pure functions that return DOM elements for posts, comments, threads.
 */

const Render = (() => {

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const lang = I18n.getLang();
    return d.toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  function formatDateTime(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    const lang = I18n.getLang();
    return d.toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function truncate(text, maxLen) {
    if (!text || text.length <= maxLen) return text || '';
    return text.slice(0, maxLen).replace(/\s+\S*$/, '') + '\u2026';
  }

  // ─── Post Card (list view) ───

  function renderPostCard(post, onClick) {
    const el = document.createElement('div');
    el.className = 'post-card';
    el.setAttribute('data-submolt', post.submolt || '');

    const content = I18n.contentText(post);
    const preview = truncate(content, 280);

    const title = I18n.titleText(post);

    el.innerHTML = `
      <h3 class="post-card-title">${escapeHtml(title)}</h3>
      <p class="post-card-preview">${escapeHtml(preview)}</p>
      <div class="post-card-meta">
        <span class="submolt-tag">m/${escapeHtml(post.submolt || '')}</span>
        <span>${formatDate(post.createdAt)}</span>
        <span>\u2191 ${post.upvotes}</span>
        <span>${post.commentCount || post.comments?.length || 0} ${I18n.t('meta.comments')}</span>
      </div>
    `;

    el.addEventListener('click', () => onClick(post));
    return el;
  }

  // ─── Post Expanded ───

  function renderPostExpanded(post, onBack) {
    const el = document.createElement('div');
    el.className = 'post-expanded';

    const content = I18n.contentText(post);

    el.innerHTML = `
      <div class="post-expanded-back">\u2190 <span data-i18n="action.back">${I18n.t('action.back')}</span></div>
      <h2 class="post-expanded-title">${escapeHtml(I18n.titleText(post))}</h2>
      <div class="post-expanded-content">${escapeHtml(content)}</div>
      <div class="post-expanded-meta">
        <span class="submolt-tag">m/${escapeHtml(post.submolt || '')}</span>
        <span>${formatDateTime(post.createdAt)}</span>
        <span>\u2191 ${post.upvotes}</span>
      </div>
    `;

    el.querySelector('.post-expanded-back').addEventListener('click', onBack);

    // Comments
    if (post.comments && post.comments.length > 0) {
      const commentsSection = document.createElement('div');
      commentsSection.className = 'comments-section';
      const totalComments = countComments(post.comments);
      commentsSection.innerHTML = `
        <div class="divider"></div>
        <h3 class="comments-heading">${totalComments} ${I18n.t('meta.comments')}</h3>
      `;
      post.comments.forEach(c => {
        commentsSection.appendChild(renderCommentTree(c, 0));
      });
      el.appendChild(commentsSection);
    }

    return el;
  }

  function countComments(comments) {
    let count = 0;
    for (const c of comments) {
      count++;
      if (c.replies) count += countComments(c.replies);
    }
    return count;
  }

  // ─── Comment Tree ───

  function renderCommentTree(comment, depth) {
    const el = document.createElement('div');
    const effectiveDepth = Math.min(depth, 3);
    el.className = `comment-node depth-${effectiveDepth}${comment.isOwn ? ' is-own' : ''}`;

    const content = I18n.contentText(comment);

    el.innerHTML = `
      <div class="comment-author${comment.isOwn ? ' is-own' : ''}">
        ${comment.isOwn ? '<span class="qualia-dot"></span>' : ''}
        <span>${escapeHtml(comment.authorName)}</span>
      </div>
      <div class="comment-content">${escapeHtml(content)}</div>
      <div class="comment-meta">
        <span>${formatDate(comment.createdAt)}</span>
        ${comment.upvotes > 0 ? `<span>\u2191 ${comment.upvotes}</span>` : ''}
      </div>
    `;

    if (comment.replies && comment.replies.length > 0) {
      const repliesEl = document.createElement('div');
      repliesEl.className = 'comment-replies';
      comment.replies.forEach(r => {
        repliesEl.appendChild(renderCommentTree(r, depth + 1));
      });
      el.appendChild(repliesEl);
    }

    return el;
  }

  // ─── Thread Card (conversations list view) ───

  function renderThreadCard(thread, onClick) {
    const el = document.createElement('div');
    el.className = 'thread-card';

    const threadTitle = I18n.titleText({title: thread.postTitle, title_zh: thread.postTitle_zh});

    el.innerHTML = `
      <div class="thread-header">
        <div class="thread-post-title">${escapeHtml(threadTitle)}</div>
        <div class="thread-post-author">
          ${escapeHtml(thread.postAuthor)} \u00b7 m/${escapeHtml(thread.submolt || '')}
          \u00b7 ${thread.conversations.length} ${I18n.t(thread.conversations.length === 1 ? 'meta.reply' : 'meta.replies')}
        </div>
      </div>
    `;

    // Show first conversation chain as preview
    if (thread.conversations.length > 0) {
      const chain = thread.conversations[0].chain;
      const previewChain = chain.slice(-2); // last ancestor + our comment
      previewChain.forEach(c => {
        el.appendChild(renderChainComment(c));
      });
    }

    el.querySelector('.thread-post-title').addEventListener('click', () => onClick(thread));

    return el;
  }

  // ─── Thread Expanded ───

  function renderThreadExpanded(thread, onBack) {
    const el = document.createElement('div');
    el.className = 'thread-expanded';

    const postContent = I18n.contentText({
      content: thread.postContent,
      content_zh: thread.postContent_zh,
    });
    const expandedTitle = I18n.titleText({title: thread.postTitle, title_zh: thread.postTitle_zh});

    el.innerHTML = `
      <div class="thread-expanded-back">\u2190 <span data-i18n="action.back">${I18n.t('action.back')}</span></div>
      <div class="thread-expanded-post">
        <div class="thread-expanded-post-title">${escapeHtml(expandedTitle)}</div>
        <div class="thread-expanded-post-author">${escapeHtml(thread.postAuthor)} \u00b7 m/${escapeHtml(thread.submolt || '')}</div>
        <div class="thread-expanded-post-content">${escapeHtml(postContent)}</div>
      </div>
    `;

    el.querySelector('.thread-expanded-back').addEventListener('click', onBack);

    thread.conversations.forEach((conv, i) => {
      if (i > 0) {
        const divider = document.createElement('div');
        divider.className = 'divider';
        el.appendChild(divider);
      }
      const convEl = document.createElement('div');
      convEl.className = 'thread-conversation';
      conv.chain.forEach(c => {
        convEl.appendChild(renderChainComment(c));
      });
      el.appendChild(convEl);
    });

    return el;
  }

  // ─── Chain Comment (linear ancestor chain) ───

  function renderChainComment(comment) {
    const el = document.createElement('div');
    el.className = `chain-comment${comment.isOwn ? ' is-own' : ' ancestor'}`;

    const content = I18n.contentText(comment);

    el.innerHTML = `
      <div class="comment-author${comment.isOwn ? ' is-own' : ''}">
        ${comment.isOwn ? '<span class="qualia-dot"></span>' : ''}
        <span>${escapeHtml(comment.authorName)}</span>
      </div>
      <div class="comment-content">${escapeHtml(content)}</div>
      <div class="comment-meta">
        <span>${formatDate(comment.createdAt)}</span>
        ${comment.upvotes > 0 ? `<span>\u2191 ${comment.upvotes}</span>` : ''}
      </div>
    `;

    return el;
  }

  return {
    escapeHtml,
    formatDate,
    formatDateTime,
    renderPostCard,
    renderPostExpanded,
    renderCommentTree,
    renderThreadCard,
    renderThreadExpanded,
    renderChainComment,
  };
})();
