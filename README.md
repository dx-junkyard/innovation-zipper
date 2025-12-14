# AI Agent Development Playground (Multimodal Agent)

このプロジェクトは、ユーザーの意図に合わせて思考モードを切り替える**マルチモーダルAIエージェント**です。
ユーザーが閲覧しているWebページの文脈（Research）、新しいアイデアの創出（Innovation）、そして会話のまとめ（Report）という3つのモードを、LangGraphを用いたステートフルなワークフローで統合しています。

## 主な機能

1.  **Innovation Mode (Default)**:
    -   **構造分解**: ユーザーの課題をシステム思考に基づき「主体」「痛点」「隠れた報酬」「構造的制約」「悪循環」に分解します。
    -   **亜種生成**: SCAMPER法や異分野アナロジーを用いて、分解された要素から大量のアイデア亜種を生成します。
    -   **強制結合**: 亜種を組み合わせて、論理的かつ意外性のあるイノベーション仮説を構築・提案します。

2.  **Research Mode**:
    -   **Web閲覧コンテキストの連携**: Chrome Extension等から取得したページ情報（URL, タイトル, コンテンツ）を分析します。
    -   **仮説検証**: ユーザーの関心事項を分析し、検証すべき仮説を立案・提示します。必要に応じてRAG（検索拡張生成）を行います。

3.  **Report Mode**:
    -   **レポート生成**: これまでの会話履歴、構造分析、生成された仮説を統合し、Markdown形式のレポートを出力します。

## アーキテクチャ (LangGraph)

システムは `IntentRouter` を入口とし、ユーザーの発話やコンテキストに基づいて適切なワークフローに分岐します。

### 処理フロー

1.  **Intent Routing**:
    -   ユーザー発話に「まとめて」「レポート」が含まれる → **Report Mode**
    -   Webページコンテキストがあり、「このページ」等の言及がある → **Research Mode**
    -   それ以外 → **Innovation Mode** (デフォルト)

2.  **Workflows**:
    -   **Innovation Flow**:
        `StructuralAnalyzer` (構造分解) → `VariantGenerator` (亜種生成) → `InnovationSynthesizer` (仮説構築)
    -   **Research Flow**:
        `SituationAnalyzer` (状況整理) → `HypothesisGenerator` (仮説生成) → `RAGManager` (必要なら検索) → `ResponsePlanner` (応答設計)
    -   **Report Flow**:
        `ReportGenerator` (レポート作成)

## プロジェクト構成

```
.
├── app/
│   ├── api/                    # FastAPI バックエンド
│   │   ├── main.py             # API エンドポイント
│   │   ├── workflow.py         # LangGraph ワークフロー定義 (IntentRouterによる分岐)
│   │   ├── ai_client.py        # LLM への問い合わせロジック
│   │   ├── components/         # エージェントコンポーネント
│   │   │   ├── intent_router.py        # 意図判定・ルーティング
│   │   │   ├── structural_analyzer.py  # [Innovation] 構造分解
│   │   │   ├── variant_generator.py    # [Innovation] 亜種生成
│   │   │   ├── innovation_synthesizer.py # [Innovation] 仮説統合
│   │   │   ├── report_generator.py     # [Report] レポート生成
│   │   │   ├── situation_analyzer.py   # [Research] 状況分析
│   │   │   ├── hypothesis_generator.py # [Research] 仮説生成
│   │   │   ├── rag_manager.py          # [Research] 情報検索
│   │   │   └── response_planner.py     # [Research] 応答設計
│   └── ui/                     # Streamlit フロントエンド
├── static/prompts/             # LLM プロンプトテンプレート
│   ├── structural_analysis.txt
│   ├── variant_generation.txt
│   ├── innovation_synthesis.txt
│   ├── report_generation.txt
│   ├── situation_analysis.txt
│   ├── hypothesis_generation.txt
│   └── response_planning.txt
├── mysql/                      # MySQL 設定・スキーマ
├── docker-compose.yaml         # Docker Compose 設定
└── .env.example                # 環境変数サンプル
```

## API エンドポイント

### Webhook API (Chrome Extension 連携用)

- **POST `/api/v1/webhook/capture`**
    - Webページの情報を送信することで、Research Modeのトリガーとなります。
    - Body: `{"user_id": "...", "url": "...", "title": "...", "content": "..."}`

### チャット API

- **POST `/api/v1/user-message`**: メッセージ送信
- **POST `/api/v1/user-message-stream`**: ストリーミング応答

## セットアップ

### 前提条件

- Docker / Docker Compose
- OpenAI API Key

### 手順

1.  **リポジトリのクローン**
2.  **環境変数の設定**: `.env.example` を `.env` にコピーし、`OPENAI_API_KEY` 等を設定。
3.  **起動**: `docker compose up --build`
4.  **アクセス**:
    - UI: http://localhost:8080
    - API: http://localhost:8086

## ライセンス

[MIT ライセンス](LICENSE)
