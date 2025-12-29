# Second Brain AI Agent

## 1. プロジェクト概要 (Introduction)

### コンセプト
本プロジェクトは、ユーザーの興味・関心を拡張し、思考の質を高めるための「第2の脳（Second Brain）」として機能する自律型AIエージェントシステムです。単なる検索エンジンやQ&Aボットとは異なり、ユーザーの思考パートナーとして「探索(Discovery)」「調査(Research)」「発想(Innovation)」の3つのモードを適応的に切り替えながら、深い洞察と新しいアイデアの創出を支援します。

### 解決する課題
現代のナレッジワーカーが直面する以下の課題を解決します：
*   **情報過多による思考の浅薄化:** 膨大な情報を整理・構造化し、本質的な「知識」へと昇華させます。
*   **ネット情報の不確実性:** 情報源の信頼性を検証し、事実（Fact）と推論（Inference）を明確に区別します。
*   **アイデアの枯渇:** 既存の知識を構造的に分解・再結合することで、予期せぬイノベーションの種を提供します。

---

## 2. システム構成 (Architecture Stack)

本システムは、モダンなマイクロサービスアーキテクチャを採用しており、スケーラビリティと保守性を重視しています。

### Application Layer
*   **Frontend:** Streamlit
    *   ユーザーとのチャットインターフェースおよび管理ダッシュボード（「Innovation Zipper」可視化など）を提供。
*   **Backend:** FastAPI
    *   REST APIおよびWebSocketによる通信、Chrome拡張機能からのデータ受信エンドポイントを提供。
*   **Agent Workflow:** LangGraph
    *   ステートフルなエージェントの思考プロセスと分岐（Intent Routing）を制御。
*   **Asynchronous Processing:** Celery + Redis
    *   ドキュメント解析、Webページ取り込み、重い推論処理をバックグラウンドで非同期実行。

### Data Persistence Layer (The "Brain")
*   **MySQL:**
    *   ユーザー管理、会話ログ、構造化データ（JSONカラムを使用した分析結果など）の保存。
*   **Qdrant (Vector DB):**
    *   RAG（Retrieval-Augmented Generation）の中核。アップロードされたPDFやWeb記事をチャンク化し、ベクトル検索を可能にします。
*   **Neo4j (Knowledge Graph):**
    *   「概念(Concept)」と「仮説(Hypothesis)」をノードとして管理。知識間の関係性（Edges）を可視化し、構造的な洞察を支援します。

---

## 3. 実装機能と特徴 (Key Features)

### マルチモーダル入力
*   **Chrome Extension Integration:** ブラウザで見ているページをワンクリックで取り込み、`SituationAnalyzer`が即座にコンテキストとして理解・記憶します。
*   **PDF Upload Pipeline:** 論文や技術資料をアップロードすると、自動的にテキスト抽出・チャンク化され、引用可能な「知識」として統合されます。

### 適応型思考ワークフロー (Adaptive Workflow)
LangGraphにより、ユーザーの意図や文脈に応じて最適な思考モードが選択されます。

1.  **Discovery Mode (探索):**
    *   ユーザーの潜在的な興味を深掘りする壁打ちパートナー。曖昧な問いに対して多角的な視点を提供します。
2.  **Research Mode (調査):**
    *   **仮説生成:** ユーザーの問いに対して初期仮説を立案。
    *   **RAG検索:** ベクトルDBから証拠となる情報を検索。
    *   **Gap分析:** 検索結果を「検証済」「推論」「要現場検証(Field-Required)」に分類し、情報の欠落を特定。
    *   **調査アクション提案:** 不足情報を補うための具体的なアクション（追加リサーチ、実地調査など）を提案。
3.  **Innovation Mode (発想):**
    *   **Structural Analysis:** 対象の概念を要素分解（構造化）。
    *   **Forced Association:** 異質な概念との強制結合やバリアント生成を行い、新しいアイデア（Innovation Hypotheses）を創出します。

### 意思決定支援
*   **ROIに基づいたアクション提案:** 情報の価値（Value of Information）と取得コストを天秤にかけ、最適な次のアクションを提案します。
*   **検証プロトコル生成:** アイデアの実効性を確かめるための具体的な検証手順（KPI、SOP）を自動生成します。

---

## 4. データ処理フロー (Data Flow)

### A. Web Capture (Chrome Ext)
1.  **Capture Request:** Chrome拡張機能からWebページのURL/Title/Contentが送信される。
2.  **API & Parsing:** FastAPIが受け取り、HTML解析と要約生成を実行。
3.  **Storage:** コンテンツを保存し、ベクトル化してQdrantへ格納。
4.  **Situation Analysis:** `SituationAnalyzer`がユーザーの興味プロファイル（Interest Profile）を更新し、コンテキストを最新化。

### B. File Upload (PDF)
1.  **User Upload:** UIからPDFをアップロード。
2.  **Processing:** `pypdf`によるテキスト抽出とチャンク化。
3.  **Knowledge Integration:** `KnowledgeManager`がチャンクをベクトル化(Qdrant)し、同時にメタデータをNeo4j上のノードとしてリンクさせる。これによりRAGでの正確な引用が可能になる。

### C. Chat Interaction
1.  **User Message:** ユーザーがメッセージを送信。
2.  **Intent Router:** 文脈とキーワードに基づき、モード（Discovery/Research/Innovation/Report）を判定。
3.  **LangGraph Workflow:**
    *   *Researchの場合:* 状況分析 → 仮説生成 → RAG → Gap分析 → 応答生成
    *   *Innovationの場合:* 構造分析 → バリアント生成 → 統合(Synthesis)
4.  **Response:** 最終的な回答と、思考プロセス（中間生成物）をStreamlitに表示。

---

## 5. セットアップと使用方法 (Getting Started)

### Prerequisites
*   Docker & Docker Compose
*   OpenAI API Key

### Installation

1.  リポジトリをクローンします。
2.  `.env` ファイルを作成し、必要な環境変数を設定します。
    ```bash
    cp .env.example .env
    # .env内のOPENAI_API_KEY等を編集してください
    ```

### Run

Docker Composeを使用してシステム全体を起動します。

```bash
docker compose up --build
```

### Access

起動後、以下のURLで各サービスにアクセスできます。

*   **User Interface (Streamlit):** `http://localhost:8080`
    *   メインのチャット画面およびダッシュボードです。
*   **API Documentation (Swagger UI):** `http://localhost:8086/docs`
    *   バックエンドAPIの仕様確認とテストが可能です。
*   **Neo4j Browser:** `http://localhost:7474`
    *   ナレッジグラフの可視化とクエリ実行が可能です。
