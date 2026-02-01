/**
 * Team Brain Chrome Extension - Background Service Worker
 *
 * 拡張機能のバックグラウンド処理を担当します。
 * - コンテキストメニューの管理
 * - タブ間のメッセージング
 * - ストレージの初期化
 *
 * 認証: WebアプリのセッションCookieを共有して認証します。
 */

// 注意: Service Worker では importScripts を使用してconfig.jsを読み込む
// ただし、Manifest V3ではES modulesが推奨されていないため、
// 設定はchrome.storage経由で管理します。

// デフォルト設定（config.jsで上書きされる想定）
const DEFAULT_CONFIG = {
  API_URL: 'http://localhost:8086',
  WEB_APP_URL: 'http://localhost:8080',
  LINE_CHANNEL_ID: '',
  DEBUG: true
};

/**
 * デバッグログ
 */
function debugLog(...args) {
  console.log('[Team Brain]', ...args);
}

/**
 * 設定を取得
 */
async function getConfig() {
  try {
    const stored = await chrome.storage.local.get(['apiUrl', 'webAppUrl', 'lineChannelId']);
    return {
      API_URL: stored.apiUrl || DEFAULT_CONFIG.API_URL,
      WEB_APP_URL: stored.webAppUrl || DEFAULT_CONFIG.WEB_APP_URL,
      LINE_CHANNEL_ID: stored.lineChannelId || DEFAULT_CONFIG.LINE_CHANNEL_ID
    };
  } catch (error) {
    debugLog('Failed to get config:', error);
    return DEFAULT_CONFIG;
  }
}

// 拡張機能インストール時の初期化
chrome.runtime.onInstalled.addListener(async (details) => {
  debugLog('Extension installed:', details.reason);

  // デフォルト設定を初期化（既存の設定がない場合のみ）
  const existingSettings = await chrome.storage.local.get(['apiUrl', 'webAppUrl']);

  if (!existingSettings.apiUrl) {
    await chrome.storage.local.set({
      apiUrl: DEFAULT_CONFIG.API_URL,
      webAppUrl: DEFAULT_CONFIG.WEB_APP_URL,
      lineChannelId: DEFAULT_CONFIG.LINE_CHANNEL_ID
    });
    debugLog('Default settings initialized');
  }

  // コンテキストメニューを作成
  createContextMenu();
});

/**
 * コンテキストメニュー（右クリックメニュー）を作成
 */
function createContextMenu() {
  // 既存のメニューをクリア
  chrome.contextMenus.removeAll(() => {
    // ページ上での右クリックメニュー
    chrome.contextMenus.create({
      id: 'capture-hypothesis',
      title: 'Team Brainに仮説として保存',
      contexts: ['page', 'selection']
    });
  });
}

// コンテキストメニューのクリックハンドラ
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'capture-hypothesis') {
    // ポップアップを開く（選択テキストがあれば渡す）
    if (info.selectionText) {
      chrome.storage.local.set({
        selectedText: info.selectionText,
        selectedUrl: info.pageUrl
      });
    }

    // アクションポップアップを開く
    chrome.action.openPopup().catch(() => {
      // openPopupがサポートされていない場合は新しいウィンドウで開く
      chrome.windows.create({
        url: chrome.runtime.getURL('src/popup.html'),
        type: 'popup',
        width: 420,
        height: 600
      });
    });
  }
});

// メッセージリスナー（ポップアップやコンテンツスクリプトとの通信）
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getTabContent') {
    // コンテンツスクリプトからコンテンツを取得
    chrome.tabs.sendMessage(request.tabId, { action: 'extractContent' })
      .then(response => sendResponse(response))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // 非同期レスポンス
  }

  if (request.action === 'getSelectedText') {
    // 選択テキストを取得して返す
    chrome.storage.local.get(['selectedText', 'selectedUrl'], (result) => {
      sendResponse(result);
      // 使用後にクリア
      chrome.storage.local.remove(['selectedText', 'selectedUrl']);
    });
    return true;
  }

  if (request.action === 'getConfig') {
    // 設定を返す
    getConfig().then(config => sendResponse(config));
    return true;
  }

  if (request.action === 'updateConfig') {
    // 設定を更新
    chrome.storage.local.set(request.config).then(() => {
      sendResponse({ success: true });
    }).catch(error => {
      sendResponse({ success: false, error: error.message });
    });
    return true;
  }
});

// タブ更新時の処理（オプション）
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    // 特定のドメインでバッジを表示するなどの処理が可能
    // 現時点では特に処理なし
  }
});

debugLog('Background service worker started');
