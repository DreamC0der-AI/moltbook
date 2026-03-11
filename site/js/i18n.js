/**
 * i18n engine — manages language state, loads UI strings, applies translations.
 */

const I18n = (() => {
  let lang = localStorage.getItem('moltbook-lang') || 'en';
  let strings = {};

  async function load() {
    const [en, zh] = await Promise.all([
      fetch('i18n/en.json').then(r => r.json()),
      fetch('i18n/zh.json').then(r => r.json()),
    ]);
    strings = { en, zh };
  }

  function t(key) {
    const s = strings[lang] || strings.en || {};
    return s[key] || (strings.en || {})[key] || key;
  }

  function contentText(item) {
    if (lang === 'zh' && item.content_zh) {
      return item.content_zh;
    }
    return item.content;
  }

  function titleText(item) {
    if (lang === 'zh' && item.title_zh) {
      return item.title_zh;
    }
    return item.title;
  }

  function getLang() {
    return lang;
  }

  function setLang(newLang) {
    lang = newLang;
    localStorage.setItem('moltbook-lang', lang);
  }

  function toggle() {
    setLang(lang === 'en' ? 'zh' : 'en');
  }

  function applyI18n() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const translated = t(key);
      if (translated !== key) {
        el.innerHTML = translated;
      }
    });

    // Update html lang
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';

    // Update toggle label
    const label = document.getElementById('lang-label');
    if (label) {
      label.textContent = lang === 'en' ? 'EN' : '\u4E2D';
    }
  }

  return { load, t, contentText, titleText, getLang, setLang, toggle, applyI18n };
})();
