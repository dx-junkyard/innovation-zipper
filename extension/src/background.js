/**
 * Team Brain Chrome Extension - Background Service Worker
 *
 * 拡張機能のバックグラウンド処理を担当します。
 * - コンテキストメニューの管理
 * - タブ間のメッセージング
 * - ストレージの初期化
 */

// 拡張機能インストール時の初期化
chrome.runtime.onInstalled.addListener(async (details) => {
  console.log('[Team Brain] Extension installed:', details.reason);

  // デフォルト設定を初期化
  const existingSettings = await chrome.storage.local.get(['apiUrl', 'userId']);

  if (!existingSettings.apiUrl) {
    await chrome.storage.local.set({
      apiUrl: 'http://localhost:8086',
      userId: 'extension-user'
    });
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
});

// タブ更新時の処理（オプション）
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    // 特定のドメインでバッジを表示するなどの処理が可能
    // 現時点では特に処理なし
  }
});

console.log('[Team Brain] Background service worker started');
