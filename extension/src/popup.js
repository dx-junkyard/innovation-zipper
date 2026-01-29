/**
 * Team Brain Chrome Extension - Popup Script
 *
 * ページ内容を解析し、AIによる仮説ドラフトを生成して
 * フォームに自動入力する機能を提供します。
 */

// デフォルト設定
const DEFAULT_SETTINGS = {
  apiUrl: 'http://localhost:8086',
  userId: 'extension-user'
};

// DOM要素の参照
const elements = {
  loading: document.getElementById('loading'),
  error: document.getElementById('error'),
  errorMessage: document.getElementById('error-message'),
  retryBtn: document.getElementById('retry-btn'),
  form: document.getElementById('hypothesis-form'),
  pageTitle: document.getElementById('page-title'),
  pageUrl: document.getElementById('page-url'),
  statement: document.getElementById('statement'),
  context: document.getElementById('context'),
  conditions: document.getElementById('conditions'),
  tags: document.getElementById('tags'),
  regenerateBtn: document.getElementById('regenerate-btn'),
  success: document.getElementById('success'),
  closeBtn: document.getElementById('close-btn'),
  settingsBtn: document.getElementById('settings-btn'),
  settingsModal: document.getElementById('settings-modal'),
  apiUrlInput: document.getElementById('api-url'),
  userIdInput: document.getElementById('user-id'),
  settingsCancel: document.getElementById('settings-cancel'),
  settingsSave: document.getElementById('settings-save')
};

// 現在のページ情報を保持
let currentPageData = null;

/**
 * 初期化処理
 */
async function initialize() {
  // 設定を読み込み
  await loadSettings();

  // イベントリスナーを設定
  setupEventListeners();

  // ページ内容を取得して解析
  await analyzeCurrentPage();
}

/**
 * 設定を読み込む
 */
async function loadSettings() {
  try {
    const result = await chrome.storage.local.get(['apiUrl', 'userId']);
    elements.apiUrlInput.value = result.apiUrl || DEFAULT_SETTINGS.apiUrl;
    elements.userIdInput.value = result.userId || DEFAULT_SETTINGS.userId;
  } catch (error) {
    console.error('Failed to load settings:', error);
  }
}

/**
 * 設定を保存する
 */
async function saveSettings() {
  const apiUrl = elements.apiUrlInput.value.trim() || DEFAULT_SETTINGS.apiUrl;
  const userId = elements.userIdInput.value.trim() || DEFAULT_SETTINGS.userId;

  try {
    await chrome.storage.local.set({ apiUrl, userId });
    hideSettingsModal();
    // 設定変更後に再解析
    await analyzeCurrentPage();
  } catch (error) {
    console.error('Failed to save settings:', error);
    alert('設定の保存に失敗しました');
  }
}

/**
 * イベントリスナーを設定
 */
function setupEventListeners() {
  // フォーム送信
  elements.form.addEventListener('submit', handleFormSubmit);

  // 再生成ボタン
  elements.regenerateBtn.addEventListener('click', handleRegenerate);

  // 再試行ボタン
  elements.retryBtn.addEventListener('click', handleRetry);

  // 閉じるボタン
  elements.closeBtn.addEventListener('click', () => window.close());

  // 設定ボタン
  elements.settingsBtn.addEventListener('click', showSettingsModal);
  elements.settingsCancel.addEventListener('click', hideSettingsModal);
  elements.settingsSave.addEventListener('click', saveSettings);

  // モーダル外クリックで閉じる
  elements.settingsModal.addEventListener('click', (e) => {
    if (e.target === elements.settingsModal) {
      hideSettingsModal();
    }
  });
}

/**
 * 設定モーダルを表示
 */
function showSettingsModal() {
  elements.settingsModal.classList.remove('hidden');
}

/**
 * 設定モーダルを非表示
 */
function hideSettingsModal() {
  elements.settingsModal.classList.add('hidden');
}

/**
 * UI状態を切り替える
 */
function showState(state) {
  elements.loading.classList.add('hidden');
  elements.error.classList.add('hidden');
  elements.form.classList.add('hidden');
  elements.success.classList.add('hidden');

  switch (state) {
    case 'loading':
      elements.loading.classList.remove('hidden');
      break;
    case 'error':
      elements.error.classList.remove('hidden');
      break;
    case 'form':
      elements.form.classList.remove('hidden');
      break;
    case 'success':
      elements.success.classList.remove('hidden');
      break;
  }
}

/**
 * 現在のページを解析
 */
async function analyzeCurrentPage() {
  showState('loading');

  try {
    // アクティブタブの情報を取得
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.id) {
      throw new Error('アクティブなタブが見つかりません');
    }

    // コンテンツスクリプトからページ内容を取得
    const pageContent = await getPageContent(tab.id);

    currentPageData = {
      url: tab.url,
      title: tab.title || 'Untitled',
      content: pageContent
    };

    // ページ情報を表示
    elements.pageTitle.textContent = currentPageData.title;
    elements.pageUrl.textContent = currentPageData.url;
    elements.pageUrl.href = currentPageData.url;

    // APIで仮説ドラフトを生成
    const draft = await generateHypothesisDraft(currentPageData);

    // フォームに入力
    populateForm(draft);

    showState('form');
  } catch (error) {
    console.error('Page analysis failed:', error);
    elements.errorMessage.textContent = error.message || '解析中にエラーが発生しました';
    showState('error');
  }
}

/**
 * コンテンツスクリプトからページ内容を取得
 */
async function getPageContent(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: extractPageContent
    });

    if (results && results[0] && results[0].result) {
      return results[0].result;
    }

    throw new Error('ページ内容の取得に失敗しました');
  } catch (error) {
    // chrome:// や edge:// などの特殊ページの場合
    if (error.message.includes('Cannot access') || error.message.includes('chrome://')) {
      throw new Error('このページは解析できません（特殊ページ）');
    }
    throw error;
  }
}

/**
 * ページからメインコンテンツを抽出する関数
 * （コンテンツスクリプトとして実行される）
 */
function extractPageContent() {
  // 不要な要素を除外するセレクタ
  const excludeSelectors = [
    'script', 'style', 'noscript', 'iframe', 'svg',
    'nav', 'header', 'footer', 'aside',
    '.sidebar', '.navigation', '.menu', '.ad', '.advertisement',
    '.comment', '.comments', '.social', '.share',
    '[role="navigation"]', '[role="banner"]', '[role="complementary"]'
  ];

  // メインコンテンツのセレクタ（優先度順）
  const mainSelectors = [
    'article',
    '[role="main"]',
    'main',
    '.post-content',
    '.article-content',
    '.entry-content',
    '.content',
    '#content',
    '.post',
    '.article'
  ];

  // メインコンテンツ要素を探す
  let mainElement = null;
  for (const selector of mainSelectors) {
    mainElement = document.querySelector(selector);
    if (mainElement) break;
  }

  // メインコンテンツが見つからない場合はbodyを使用
  const targetElement = mainElement || document.body;

  // クローンを作成して不要な要素を削除
  const clone = targetElement.cloneNode(true);

  for (const selector of excludeSelectors) {
    const elements = clone.querySelectorAll(selector);
    elements.forEach(el => el.remove());
  }

  // テキストを抽出
  let text = clone.innerText || clone.textContent || '';

  // 空白行を整理
  text = text
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0)
    .join('\n');

  // 最大文字数を制限（APIへの送信サイズを考慮）
  const maxLength = 10000;
  if (text.length > maxLength) {
    text = text.substring(0, maxLength) + '...';
  }

  return text;
}

/**
 * APIを呼び出して仮説ドラフトを生成
 */
async function generateHypothesisDraft(pageData) {
  const settings = {
    apiUrl: elements.apiUrlInput.value.trim() || DEFAULT_SETTINGS.apiUrl,
    userId: elements.userIdInput.value.trim() || DEFAULT_SETTINGS.userId
  };

  const response = await fetch(`${settings.apiUrl}/api/v1/hypothesis/draft`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      url: pageData.url,
      title: pageData.title,
      content: pageData.content,
      user_id: settings.userId
    })
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `APIエラー: ${response.status}`);
  }

  return await response.json();
}

/**
 * フォームにデータを入力
 */
function populateForm(draft) {
  elements.statement.value = draft.statement || '';
  elements.context.value = draft.context || '';
  elements.conditions.value = draft.conditions || '';
  elements.tags.value = (draft.tags || []).join(', ');
}

/**
 * 再生成ハンドラ
 */
async function handleRegenerate() {
  elements.regenerateBtn.disabled = true;
  elements.regenerateBtn.textContent = '生成中...';

  try {
    const draft = await generateHypothesisDraft(currentPageData);
    populateForm(draft);
  } catch (error) {
    console.error('Regeneration failed:', error);
    alert('再生成に失敗しました: ' + error.message);
  } finally {
    elements.regenerateBtn.disabled = false;
    elements.regenerateBtn.textContent = '再生成';
  }
}

/**
 * 再試行ハンドラ
 */
async function handleRetry() {
  await analyzeCurrentPage();
}

/**
 * フォーム送信ハンドラ
 */
async function handleFormSubmit(event) {
  event.preventDefault();

  const submitBtn = event.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.textContent = '保存中...';

  try {
    const settings = {
      apiUrl: elements.apiUrlInput.value.trim() || DEFAULT_SETTINGS.apiUrl,
      userId: elements.userIdInput.value.trim() || DEFAULT_SETTINGS.userId
    };

    // タグを配列に変換
    const tagsInput = elements.tags.value.trim();
    const tags = tagsInput
      ? tagsInput.split(',').map(t => t.trim()).filter(t => t.length > 0)
      : [];

    // 仮説を保存
    const response = await fetch(`${settings.apiUrl}/api/v1/team-brain/hypotheses/incubate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_id: settings.userId,
        experience: `【URL】${currentPageData.url}\n【タイトル】${currentPageData.title}\n\n【仮説】\n${elements.statement.value}\n\n【背景・文脈】\n${elements.context.value}\n\n【成立条件】\n${elements.conditions.value}`,
        auto_score: true,
        check_sharing: false
      })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `保存に失敗しました: ${response.status}`);
    }

    showState('success');
  } catch (error) {
    console.error('Save failed:', error);
    alert('保存に失敗しました: ' + error.message);
    submitBtn.disabled = false;
    submitBtn.textContent = '保存';
  }
}

// 初期化を実行
document.addEventListener('DOMContentLoaded', initialize);
