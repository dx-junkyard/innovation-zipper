# AI Agent Development Playground (Multimodal Agent)

このプロジェクトは、ユーザーとの対話を通じて「没入感（Immersion）」と「真実への接近（Truth）」のスイートスポットを探り、最適な思考モードへ誘導するマルチモーダルAIエージェントです。

## モード構成

1.  **Discovery Mode (Default)**:
    -   **探索**: ユーザーとの雑談を通じて、個人的な熱量（Immersion）と構造的な課題（Truth）が交差するテーマを探ります。
    -   **誘導**: 機運が高まった段階で、解決（Innovation）や調査（Research）への移行を提案します。

2.  **Innovation Mode**:
    -   **構造分解・発想**: 課題をシステム思考で分解し、強制発想によりイノベーティブな仮説を生成します。

3.  **Research Mode**:
    -   **調査・検証**: Webページ情報やRAGを用いて、仮説の事実確認を行います。

4.  **Report Mode**:
    -   **統合**: 議論の成果をレポートとして出力します。

## アーキテクチャ (LangGraph)

システムは `IntentRouter` を入口とし、ユーザーの発話やコンテキストに基づいて適切なワークフローに分岐します。

### 処理フロー

1.  **Intent Routing**:
    -   ユーザー発話に「まとめて」「レポート」が含まれる → **Report Mode**
    -   Webページコンテキストがあり、「このページ」等の言及がある → **Research Mode**
    -   「課題解決」「ブレスト」等の強い開始意志がある → **Innovation Mode**
    -   それ以外 → **Discovery Mode** (デフォルト)

2.  **Workflows**:
    -   **Discovery Flow**:
        `InterestExplorer` (関心探索)
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
│   │   │   ├── interest_explorer.py    # [Discovery] 関心探索 (New)
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
│   ├── interest_exploration.txt # (New)
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
