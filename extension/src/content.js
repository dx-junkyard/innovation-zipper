/**
 * Team Brain Chrome Extension - Content Script
 *
 * ページのDOMにアクセスし、主要なテキストコンテンツを抽出します。
 * このスクリプトはmanifest.jsonで全URLに対して自動注入されます。
 */

// メッセージリスナーを設定（バックグラウンドスクリプトからの要求に応答）
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractContent') {
    try {
      const content = extractMainContent();
      sendResponse({ success: true, content });
    } catch (error) {
      sendResponse({ success: false, error: error.message });
    }
    return true; // 非同期レスポンスを示す
  }
});

/**
 * ページからメインコンテンツを抽出
 * @returns {Object} 抽出されたコンテンツ
 */
function extractMainContent() {
  // メタ情報を取得
  const meta = extractMetaInfo();

  // メインテキストを抽出
  const text = extractBodyText();

  // 構造化データを抽出（あれば）
  const structuredData = extractStructuredData();

  return {
    meta,
    text,
    structuredData
  };
}

/**
 * メタ情報を抽出
 */
function extractMetaInfo() {
  const getMetaContent = (name) => {
    const meta = document.querySelector(
      `meta[name="${name}"], meta[property="${name}"], meta[property="og:${name}"]`
    );
    return meta ? meta.getAttribute('content') : null;
  };

  return {
    title: document.title,
    description: getMetaContent('description') || getMetaContent('og:description'),
    keywords: getMetaContent('keywords'),
    author: getMetaContent('author'),
    publishedTime: getMetaContent('article:published_time'),
    siteName: getMetaContent('og:site_name')
  };
}

/**
 * 本文テキストを抽出
 */
function extractBodyText() {
  // 不要な要素のセレクタ
  const excludeSelectors = [
    'script', 'style', 'noscript', 'iframe', 'svg', 'canvas',
    'nav', 'header', 'footer', 'aside',
    '.sidebar', '.navigation', '.nav', '.menu',
    '.ad', '.ads', '.advertisement', '.sponsored',
    '.comment', '.comments', '.comment-section',
    '.social', '.share', '.sharing',
    '.related', '.recommended',
    '.cookie', '.popup', '.modal',
    '[role="navigation"]', '[role="banner"]', '[role="complementary"]',
    '[aria-hidden="true"]'
  ];

  // メインコンテンツの候補セレクタ（優先度順）
  const mainSelectors = [
    'article',
    '[role="main"]',
    'main',
    '.post-content',
    '.article-content',
    '.article-body',
    '.entry-content',
    '.content-body',
    '.story-content',
    '.post-body',
    '#article-body',
    '.content',
    '#content'
  ];

  // メインコンテンツ要素を探す
  let mainElement = null;
  for (const selector of mainSelectors) {
    mainElement = document.querySelector(selector);
    if (mainElement && mainElement.innerText.trim().length > 200) {
      break;
    }
  }

  // 見つからない場合はbodyを使用
  const targetElement = mainElement || document.body;

  // クローンを作成
  const clone = targetElement.cloneNode(true);

  // 不要な要素を削除
  for (const selector of excludeSelectors) {
    try {
      const elements = clone.querySelectorAll(selector);
      elements.forEach(el => el.remove());
    } catch (e) {
      // セレクタエラーを無視
    }
  }

  // テキストを抽出・整形
  let text = clone.innerText || clone.textContent || '';

  // 複数の空白行を1つに
  text = text.replace(/\n{3,}/g, '\n\n');

  // 行ごとにトリム
  text = text
    .split('\n')
    .map(line => line.trim())
    .join('\n');

  // 連続する空白を1つに
  text = text.replace(/[ \t]+/g, ' ');

  return text.trim();
}

/**
 * JSON-LD構造化データを抽出
 */
function extractStructuredData() {
  const scripts = document.querySelectorAll('script[type="application/ld+json"]');
  const data = [];

  scripts.forEach(script => {
    try {
      const parsed = JSON.parse(script.textContent);
      data.push(parsed);
    } catch (e) {
      // パースエラーを無視
    }
  });

  return data.length > 0 ? data : null;
}

// ページ読み込み完了を通知（オプション）
console.log('[Team Brain Extension] Content script loaded');
