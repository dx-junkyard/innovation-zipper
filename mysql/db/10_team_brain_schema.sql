-- =============================================================================
-- Team Brain Schema: 仮説の共創と検証の循環
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Teams Table: チーム管理
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by VARCHAR(36) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_teams_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- Team Members Table: チームメンバー関連
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_members (
    team_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    role ENUM('owner', 'editor', 'viewer') DEFAULT 'viewer',
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, user_id),
    CONSTRAINT fk_team_members_team FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    CONSTRAINT fk_team_members_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- Hypotheses Table: 仮説管理テーブル (Data Model from Requirements)
-- -----------------------------------------------------------------------------
-- status: DRAFT(個人), PROPOSED(承認待ち), SHARED(公開)
-- verification_state: UNVERIFIED, IN_PROGRESS, VALIDATED, FAILED
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hypotheses (
    id VARCHAR(36) NOT NULL,
    origin_user_id VARCHAR(36) NOT NULL,
    origin_user_id_hash VARCHAR(64),                   -- 匿名化用ハッシュ
    team_id VARCHAR(36),                               -- 所属チーム（SHARED時に設定）
    content TEXT NOT NULL,                             -- 仮説の内容（構造化テキスト）
    original_experience TEXT,                          -- 元の経験メモ
    status ENUM('DRAFT', 'PROPOSED', 'SHARED') NOT NULL DEFAULT 'DRAFT',
    verification_state ENUM('UNVERIFIED', 'IN_PROGRESS', 'VALIDATED', 'FAILED') NOT NULL DEFAULT 'UNVERIFIED',
    quality_score JSON,                                -- AIによる「筋の良さ」スコア
    parent_hypothesis_id VARCHAR(36),                  -- 派生元の仮説ID
    tags JSON,                                         -- カテゴリタグ
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    shared_at DATETIME,                                -- 公開日時
    PRIMARY KEY (id),
    INDEX idx_hypotheses_user (origin_user_id),
    INDEX idx_hypotheses_team (team_id),
    INDEX idx_hypotheses_status (status),
    INDEX idx_hypotheses_verification (verification_state),
    INDEX idx_hypotheses_parent (parent_hypothesis_id),
    CONSTRAINT fk_hypotheses_user FOREIGN KEY (origin_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_hypotheses_team FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL,
    CONSTRAINT fk_hypotheses_parent FOREIGN KEY (parent_hypothesis_id) REFERENCES hypotheses(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- Hypothesis Verifications Table: 検証結果ログ
-- -----------------------------------------------------------------------------
-- 誰が（あるいはどの部署が）どこまで検証したかという履歴
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hypothesis_verifications (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    hypothesis_id VARCHAR(36) NOT NULL,
    verifier_user_id VARCHAR(36) NOT NULL,
    verifier_team_id VARCHAR(36),                      -- 検証者の所属チーム
    verification_result ENUM('SUCCESS', 'FAILURE', 'PARTIAL', 'INCONCLUSIVE') NOT NULL,
    conditions TEXT,                                   -- 検証時の条件
    notes TEXT,                                        -- 検証メモ・詳細
    evidence JSON,                                     -- 検証の根拠データ
    is_differential BOOLEAN DEFAULT FALSE,             -- 差分検証かどうか (FR-402)
    parent_verification_id BIGINT UNSIGNED,            -- 差分の場合の親検証ID
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_verifications_hypothesis (hypothesis_id),
    INDEX idx_verifications_user (verifier_user_id),
    INDEX idx_verifications_team (verifier_team_id),
    INDEX idx_verifications_result (verification_result),
    CONSTRAINT fk_verifications_hypothesis FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id) ON DELETE CASCADE,
    CONSTRAINT fk_verifications_user FOREIGN KEY (verifier_user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_verifications_team FOREIGN KEY (verifier_team_id) REFERENCES teams(id) ON DELETE SET NULL,
    CONSTRAINT fk_verifications_parent FOREIGN KEY (parent_verification_id) REFERENCES hypothesis_verifications(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- Sharing Suggestions Table: 共有サジェスト履歴 (FR-202)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sharing_suggestions (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    hypothesis_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    suggestion_reason TEXT,                            -- サジェスト理由
    draft_content TEXT,                                -- 匿名化済みドラフト
    status ENUM('PENDING', 'ACCEPTED', 'REJECTED', 'EDITED') NOT NULL DEFAULT 'PENDING',
    edited_content TEXT,                               -- ユーザー編集後の内容
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    responded_at DATETIME,
    PRIMARY KEY (id),
    INDEX idx_suggestions_hypothesis (hypothesis_id),
    INDEX idx_suggestions_user (user_id),
    INDEX idx_suggestions_status (status),
    CONSTRAINT fk_suggestions_hypothesis FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id) ON DELETE CASCADE,
    CONSTRAINT fk_suggestions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- Hypothesis Quality Scores Detail Table: 品質スコア詳細 (FR-201)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hypothesis_quality_scores (
    id BIGINT UNSIGNED AUTO_INCREMENT,
    hypothesis_id VARCHAR(36) NOT NULL,
    novelty_score DECIMAL(3,2),                        -- 新規性 (0.00-1.00)
    specificity_score DECIMAL(3,2),                    -- 具体性 (0.00-1.00)
    impact_score DECIMAL(3,2),                         -- 組織への影響度 (0.00-1.00)
    overall_score DECIMAL(3,2),                        -- 総合スコア (0.00-1.00)
    is_high_potential BOOLEAN DEFAULT FALSE,           -- 「筋が良い」判定
    scoring_rationale TEXT,                            -- スコアリング根拠
    scored_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_quality_hypothesis (hypothesis_id),
    INDEX idx_quality_potential (is_high_potential),
    CONSTRAINT fk_quality_hypothesis FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
