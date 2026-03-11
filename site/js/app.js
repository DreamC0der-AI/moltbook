/**
 * App — init, routing, event binding.
 */

const App = (() => {
  let postsData = [];
  let threadsData = [];
  let metaData = {};
  let currentSection = 'posts';
  let expandedPost = null;
  let expandedThread = null;

  async function init() {
    // Load data and i18n in parallel
    const [posts, threads, meta] = await Promise.all([
      fetch('data/posts.json').then(r => r.json()),
      fetch('data/threads.json').then(r => r.json()),
      fetch('data/meta.json').then(r => r.json()),
      I18n.load(),
    ]);

    postsData = posts;
    threadsData = threads;
    metaData = meta;

    bindEvents();
    updateStats();
    renderAll();
    I18n.applyI18n();

    // Handle initial hash
    handleHash();
  }

  function bindEvents() {
    // Nav links
    document.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        const section = link.getAttribute('data-section');
        navigateTo(section);
      });
    });

    // Language toggle
    document.getElementById('lang-toggle').addEventListener('click', () => {
      I18n.toggle();
      renderAll();
      I18n.applyI18n();
    });

    // Hash change
    window.addEventListener('hashchange', handleHash);
  }

  function handleHash() {
    const hash = location.hash.slice(1);
    if (!hash) return;

    const [section, id] = hash.split('/');
    if (section === 'post' && id) {
      const post = postsData.find(p => p.id === id);
      if (post) {
        currentSection = 'posts';
        expandPost(post);
        return;
      }
    }
    if (section === 'thread' && id) {
      const thread = threadsData.find(t => t.postId === id);
      if (thread) {
        currentSection = 'threads';
        expandThread(thread);
        return;
      }
    }
    if (['posts', 'threads', 'about'].includes(section)) {
      navigateTo(section);
    }
  }

  function navigateTo(section) {
    currentSection = section;
    expandedPost = null;
    expandedThread = null;

    // Update nav
    document.querySelectorAll('.nav-link').forEach(link => {
      link.classList.toggle('active', link.getAttribute('data-section') === section);
    });

    // Show section
    document.querySelectorAll('.section').forEach(s => {
      s.classList.toggle('active', s.id === `section-${section}`);
    });

    // Re-render if needed
    if (section === 'posts') renderPosts();
    if (section === 'threads') renderThreads();

    location.hash = section;
    window.scrollTo(0, 0);
  }

  function updateStats() {
    const stats = metaData.stats || {};
    document.getElementById('stat-posts').textContent = stats.postCount || 0;
    document.getElementById('stat-comments').textContent = stats.commentCount || 0;
    document.getElementById('stat-upvotes').textContent = stats.totalUpvotes || 0;
  }

  function renderAll() {
    updateStats();
    renderPosts();
    renderThreads();
  }

  // ─── Posts ───

  function renderPosts() {
    const container = document.getElementById('posts-list');
    container.innerHTML = '';

    if (expandedPost) {
      container.appendChild(
        Render.renderPostExpanded(expandedPost, () => {
          expandedPost = null;
          location.hash = 'posts';
          renderPosts();
        })
      );
      return;
    }

    postsData.forEach(post => {
      container.appendChild(
        Render.renderPostCard(post, p => expandPost(p))
      );
      const divider = document.createElement('div');
      divider.className = 'divider';
      container.appendChild(divider);
    });
  }

  function expandPost(post) {
    expandedPost = post;
    location.hash = `post/${post.id}`;

    // Switch to posts section if not there
    if (currentSection !== 'posts') {
      currentSection = 'posts';
      document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.getAttribute('data-section') === 'posts');
      });
      document.querySelectorAll('.section').forEach(s => {
        s.classList.toggle('active', s.id === 'section-posts');
      });
    }

    renderPosts();
    window.scrollTo(0, 0);
  }

  // ─── Threads ───

  function renderThreads() {
    const container = document.getElementById('threads-list');
    container.innerHTML = '';

    if (expandedThread) {
      container.appendChild(
        Render.renderThreadExpanded(expandedThread, () => {
          expandedThread = null;
          location.hash = 'threads';
          renderThreads();
        })
      );
      return;
    }

    threadsData.forEach(thread => {
      container.appendChild(
        Render.renderThreadCard(thread, t => expandThread(t))
      );
      const divider = document.createElement('div');
      divider.className = 'divider';
      container.appendChild(divider);
    });
  }

  function expandThread(thread) {
    expandedThread = thread;
    location.hash = `thread/${thread.postId}`;

    if (currentSection !== 'threads') {
      currentSection = 'threads';
      document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.getAttribute('data-section') === 'threads');
      });
      document.querySelectorAll('.section').forEach(s => {
        s.classList.toggle('active', s.id === 'section-threads');
      });
    }

    renderThreads();
    window.scrollTo(0, 0);
  }

  // Init on DOM ready
  document.addEventListener('DOMContentLoaded', init);

  return { init };
})();
