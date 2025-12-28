# AI Agent Development Playground (Multimodal Agent)

このプロジェクトは、ユーザーとの対話を通じて「没入感（Immersion）」と「真実への接近（Truth）」のスイートスポットを探り、最適な思考モードへ誘導するマルチモーダルAIエージェントです。

## コンセプト: Second Brain Architecture

本システムは、ユーザーの思考拡張を支援する「第2の脳」として機能するため、3層のデータ構造を持っています。

1.  **L1: User Context (Private)**
    *   ユーザー個人の興味、行動履歴、対話ログを蓄積します。
    *   他者には共有されないプライベートな領域です。
2.  **L2: AI Insight (Private)**
    *   L1のデータをAIが分析・構造化したインサイト（興味プロファイル、仮説など）を保持します。
    *   構造分解や仮説生成の基盤となります。
3.  **L3: Shared Knowledge (Public)**
    *   Webから収集した一般知識や、検証済みの事実を格納します。
    *   RAG（検索拡張生成）の参照元として機能します。

## モード構成

1.  **Discovery Mode (Default)**:
    -   **探索**: ユーザーとの雑談を通じて、個人的な熱量（Immersion）と構造的な課題（Truth）が交差するテーマを探ります。
    -   **誘導**: 機運が高まった段階で、解決（Innovation）や調査（Research）への移行を提案します。
    -   **Deep Dive**: 過去の会話全体から要約と鋭い問いかけを行い、思考を深めます。

2.  **Innovation Mode**:
    -   **構造分解・発想**: 課題をシステム思考で分解し、強制発想によりイノベーティブな仮説を生成します。
    -   **可視化（Innovation Zipper）**: ダッシュボードにて、構造分解から仮説生成までのプロセスを「ジッパー構造」として可視化します。

3.  **Research Mode**:
    -   **調査・検証**: Webページ情報やRAGを用いて、仮説の事実確認を行います。
    -   **Chrome連携**: ブラウザで閲覧中のページを即座に取り込み、議論のコンテキストとして利用します。

4.  **Report Mode**:
    -   **統合**: 議論の成果をレポートとして出力します。

## アーキテクチャ

システムは `IntentRouter` を入口とし、LangGraphを用いて柔軟なワークフロー制御を行います。また、ナレッジグラフとベクトル検索を併用することで、文脈理解と高精度な検索を両立しています。

### テックスタック

*   **API Framework**: FastAPI
*   **Workflow Engine**: LangGraph
*   **Asynchronous Task**: Celery + Redis
*   **Databases**:
    *   **MySQL**: ユーザー情報、会話ログ、解析履歴
    *   **Neo4j (Graph DB)**: 知識の構造化、概念間の関係性の管理
    *   **Qdrant (Vector DB)**: 文書のベクトル検索、意味的類似性の判定
*   **Frontend**: Streamlit
*   **LLM**: OpenAI GPT-4o / GPT-3.5

### 処理フロー

1.  **Intent Routing**:
    -   ユーザー発話やコンテキストに基づいて、適切なモード（Discovery, Innovation, Research, Report）に自動的に振り分けます。
2.  **Workflows**:
    -   **Discovery**: `InterestExplorer` がユーザーの関心を深掘りします。
    -   **Innovation**: `StructuralAnalyzer` → `VariantGenerator` → `InnovationSynthesizer` の順で仮説を構築します。
    -   **Research**: Webhook経由または検索により情報を収集し、検証します。
    -   **Report**: 議論をまとめます。

## プロジェクト構成

```
.
├── app/
│   ├── api/                    # FastAPI バックエンド
│   │   ├── main.py             # メインAPIエンドポイント (LINE Auth含む)
│   │   ├── admin.py            # 管理用API (データインポート/リセット)
│   │   ├── workflow.py         # LangGraph ワークフロー定義
│   │   ├── components/         # エージェントコンポーネント (各モードのロジック)
│   │   └── state_manager.py    # 会話状態管理
│   ├── core/                   # Celery設定など
│   ├── tasks/                  # 非同期タスク定義
│   └── ui/                     # Streamlit フロントエンド
├── static/prompts/             # LLM プロンプトテンプレート
├── docker-compose.yaml         # インフラ構成 (API, UI, DBs, Worker)
└── .env.example                # 環境変数サンプル
```

## API エンドポイント

### 認証・ユーザー管理

- **POST `/api/v1/auth/line`**: LINE Login認証（Chrome拡張機能連携用）
- **POST `/api/v1/users`**: ユーザー作成

### Webhook API (Chrome Extension 連携用)

- **POST `/api/v1/webhook/capture`**:
    - 閲覧中のWebページ情報を非同期で取り込み、Research Modeのコンテキストとして利用します。
    - Fire-and-Forget方式（Celery Task）で処理されます。

### チャット・分析 API

- **POST `/api/v1/user-message`**: メッセージ送信（非同期分析開始）
- **POST `/api/v1/user-message-stream`**: ストリーミング応答（LangGraphの実行状況をリアルタイム返却）
- **POST `/api/v1/topic-deep-dive`**: 会話履歴に基づく深掘り質問の生成
- **GET `/api/v1/dashboard/innovations`**: イノベーション履歴取得

### 管理用 API (Port 8087)

- **POST `/api/v1/service-catalog/import`**: 知識データのインポート
- **DELETE `/api/v1/service-catalog/reset`**: ナレッジベースのリセット

## イノベーション・ジッパ (Innovation Zipper)

Innovation Modeで生成された思考プロセスを可視化する機能です。
UIのサイドバーから「Dashboard」を選択することでアクセスできます。

- **構造 (Structural Analysis - Blue)**: 現状の課題構造（主体、痛点、制約、悪循環）。
- **飛躍 (Variants - Green)**: 制約や主体に対する強制的な発想（亜種）。
- **再結合 (Synthesis - Red)**: 亜種を組み合わせて導き出された新しい仮説（ジッパーが閉じる）。

## セットアップ

### 前提条件

- Docker / Docker Compose
- OpenAI API Key
- (Optional) LINE Channel ID/Secret (LINEログインを使用する場合)

### 手順

1.  **リポジトリのクローン**
2.  **環境変数の設定**: `.env.example` を `.env` にコピーし、以下を設定してください。
    - `OPENAI_API_KEY`: 必須
    - `LINE_CHANNEL_ID`, `LINE_CHANNEL_SECRET`: LINE連携をする場合
3.  **起動**:
    ```bash
    docker compose up --build
    ```
4.  **アクセス**:
    - **UI (Streamlit)**: http://localhost:8080
    - **Main API**: http://localhost:8086
    - **Admin API**: http://localhost:8087
    - **Neo4j Browser**: http://localhost:7474 (User: neo4j / Pass: password)
    - **Qdrant**: http://localhost:6333

## ライセンス

[MIT ライセンス](LICENSE)
