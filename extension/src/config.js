/**
 * Team Brain Extension - Configuration
 *
 * このファイルはBackendの動的ZIP生成時に上書きされます。
 * ローカル開発時はこのデフォルト値が使用されます。
 */

// eslint-disable-next-line no-unused-vars
const TEAM_BRAIN_CONFIG = {
  // API Base URL (末尾スラッシュなし)
  API_URL: 'http://localhost:8086',

  // LINE Channel ID (LINEログイン用)
  LINE_CHANNEL_ID: '',

  // Web App URL (セッション共有元のURL)
  WEB_APP_URL: 'http://localhost:8080',

  // 拡張機能バージョン
  VERSION: '1.0.0',

  // デバッグモード
  DEBUG: true
};

// ES Module export (manifest v3では使用不可のため、グローバル変数として公開)
if (typeof window !== 'undefined') {
  window.TEAM_BRAIN_CONFIG = TEAM_BRAIN_CONFIG;
}
