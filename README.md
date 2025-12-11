# AI Agent 開発講座（仮説検証エージェント編）

このプロジェクトは、**ユーザーの関心に基づいた仮説検証**を支援する、AI エージェント対話型 Web アプリケーションです。
Chrome Extension などからユーザーが閲覧している Web ページの情報を取得し、その文脈とユーザーとの対話を通じて、ユーザーが抱いている疑問や仮説を明確化・検証します。

バックエンドは **LangGraph** を用いたコンポーネントベースのアーキテクチャを採用しており、状況分析、仮説生成、検証計画、応答生成といったプロセスを構造化して実行します。

## 主な機能

- **Web 閲覧コンテキストの連携**: Webhook API を通じて、ユーザーが閲覧中のページ情報（URL, タイトル, コンテンツ）を取り込みます。
- **仮説検証ワークフロー**: ユーザーの関心事項を分析し、検証すべき仮説を立案・提示します。
- **Streamlit チャット UI**: リアルタイムで AI と対話し、思考プロセス（状況整理、仮説生成など）を可視化します。
- **LINE ログイン**: ユーザー認証を行い、会話履歴や分析結果（興味プロファイル、アクティブな仮説）を保存します。

## プロジェクト構成

```
.
├── app/
│   ├── api/                    # FastAPI バックエンド
│   │   ├── main.py             # API エンドポイント
│   │   ├── workflow.py         # LangGraph ワークフロー定義
│   │   ├── ai_client.py        # LLM への問い合わせロジック
│   │   ├── db.py               # MySQL とのやり取り
│   │   ├── state_manager.py    # 状態管理 (Interest Profile, Hypotheses)
│   │   └── components/         # エージェントコンポーネント
│   │       ├── situation_analyzer.py   # 興味・関心の分析
│   │       ├── hypothesis_generator.py # 検証仮説の生成
│   │       ├── rag_manager.py          # 情報検索 (RAG - オプション)
│   │       └── response_planner.py     # 応答設計
│   └── ui/                     # Streamlit フロントエンド
│       ├── ui.py               # チャット画面
│       └── line_login.py       # LINE ログインフロー
├── static/prompts/             # LLM プロンプトテンプレート
├── mysql/
│   ├── my.cnf                  # MySQL 設定
│   └── db/
│       ├── schema.sql          # ユーザー・状態管理テーブル DDL
│       ├── captured_pages.sql  # Webhook で受信したページ情報 DDL
│       └── user_messages.sql   # メッセージ履歴 DDL
├── scripts/                # スクリプト群
├── config.py                   # アプリ共通設定
├── requirements.api.txt        # API 用 Python 依存関係
├── requirements.ui.txt         # UI 用 Python 依存関係
├── Dockerfile.api              # API 用 Dockerfile
├── Dockerfile.ui               # UI 用 Dockerfile
├── docker-compose.yaml         # Docker Compose 設定
└── .env.example                # 環境変数サンプル
```

## バックエンドアーキテクチャ (LangGraph)

ユーザーからのメッセージや Webhook からの情報を受け取り、以下のフローを実行します。

1.  **SituationAnalyzer（状況分析）**:
    - 閲覧中の Web ページと会話履歴から、ユーザーの**興味プロファイル (Interest Profile)** と **アクティブな仮説 (Active Hypotheses)** を更新します。
2.  **HypothesisGenerator（仮説生成）**:
    - 分析された興味に基づき、検証可能で具体的な仮説を生成します。
    - 外部情報の検索が必要かどうかも判断します。
3.  **RAGManager（情報検索 - 条件付き）**:
    - 必要に応じて外部情報（※現在は旧サービスカタログ連携の名残）を検索します。
4.  **ResponsePlanner（応答設計）**:
    - 仮説を検証するための次のアクションや質問をユーザーに提示します。

## API エンドポイント

### Webhook API (Chrome Extension 連携用)

Web ページの情報をエージェントに送信します。

- **POST `/api/v1/webhook/capture`**
    - Body: `{"user_id": "...", "url": "...", "title": "...", "content": "..."}`
    - これにより、エージェントはユーザーが見ているページの内容を踏まえて回答できるようになります。

### チャット API

- **POST `/api/v1/user-message`**: メッセージ送信（同期）
- **POST `/api/v1/user-message-stream`**: メッセージ送信（ストリーミング応答）

## セットアップ

### 前提条件

- Docker / Docker Compose
- OpenAI API Key または Ollama
- LINE ログインチャネル

### セットアップ手順

1. **リポジトリのクローン**
    ```bash
    git clone https://github.com/dx-junkyard/ai-agent-playground-101.git
    cd ai-agent-playground-101
    ```

2. **環境変数の設定**
    - `.env.example` を `.env` にコピーし、`OPENAI_API_KEY` 等を設定します。

3. **コンテナの起動**
    ```bash
    docker compose up --build
    ```

4. **アプリケーションへのアクセス**
    - UI: http://localhost:8080
    - API: http://localhost:8086

## 使い方

1. ブラウザで http://localhost:8080 にアクセスし、LINE ログインします。
2. Chrome Extension (別リポジトリ) 等から Web ページ情報を `/api/v1/webhook/capture` に送信します（または curl で模擬送信）。
3. チャット画面で「このページについてどう思う？」「何が問題なの？」といった質問を投げかけます。
4. AI がページの内容とユーザーの関心を分析し、検証すべきポイントを提示します。

## ライセンス

[MIT ライセンス](LICENSE)
