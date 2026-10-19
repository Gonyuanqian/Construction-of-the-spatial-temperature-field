-- Preserve existing model IDs, JSON and binary artifacts. New installations use the same schema.
CREATE TABLE IF NOT EXISTS model (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    saved_at DATETIME NOT NULL,
    dataset_sig VARCHAR(64) NOT NULL,
    groups_sig CHAR(8) NOT NULL,
    data_file VARCHAR(255) NOT NULL,
    data_start DATETIME NOT NULL,
    data_end DATETIME NOT NULL,
    mae DOUBLE NULL,
    rmse DOUBLE NULL,
    r2 DOUBLE NULL,
    is_current TINYINT(1) NOT NULL DEFAULT 0,
    bundle LONGTEXT NOT NULL,
    artifact LONGBLOB NULL,
    KEY idx_current (is_current)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Older installations may predate the artifact column. No existing payload is rewritten.
SET @tfield_artifact_ddl = (
    SELECT IF(COUNT(*)=0, 'ALTER TABLE model ADD COLUMN artifact LONGBLOB NULL AFTER bundle', 'SELECT 1')
    FROM information_schema.columns
    WHERE table_schema=DATABASE() AND table_name='model' AND column_name='artifact'
);
PREPARE tfield_artifact_statement FROM @tfield_artifact_ddl;
EXECUTE tfield_artifact_statement;
DEALLOCATE PREPARE tfield_artifact_statement;

CREATE TABLE training_job (
    id CHAR(36) NOT NULL PRIMARY KEY,
    dataset_id CHAR(36) NOT NULL,
    request_key VARCHAR(128) NULL,
    config_json LONGTEXT NOT NULL,
    config_sha256 CHAR(64) NOT NULL,
    state VARCHAR(16) NOT NULL,
    progress TEXT NOT NULL,
    error TEXT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    finished_at TIMESTAMP(6) NULL,
    elapsed_s DOUBLE NOT NULL DEFAULT 0,
    python_instance_id CHAR(36) NOT NULL,
    cancel_requested TINYINT(1) NOT NULL DEFAULT 0,
    result_retired TINYINT(1) NOT NULL DEFAULT 0,
    saved_model_id BIGINT NULL,
    bundle_sha256 CHAR(64) NULL,
    artifact_sha256 CHAR(64) NULL,
    running_slot TINYINT GENERATED ALWAYS AS (CASE WHEN state='running' THEN 1 ELSE NULL END) STORED,
    UNIQUE KEY uq_training_request (request_key),
    UNIQUE KEY uq_training_running (running_slot),
    UNIQUE KEY uq_training_saved_model (saved_model_id),
    KEY idx_training_dataset (dataset_id,created_at),
    CONSTRAINT fk_training_dataset FOREIGN KEY (dataset_id) REFERENCES dataset_record(id),
    CONSTRAINT fk_training_model FOREIGN KEY (saved_model_id) REFERENCES model(id),
    CONSTRAINT ck_training_state CHECK (state IN ('running','done','failed','cancelled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE workspace_context
    ADD COLUMN model_id BIGINT NULL,
    ADD COLUMN latest_job_id CHAR(36) NULL,
    ADD COLUMN result_job_id CHAR(36) NULL,
    ADD CONSTRAINT fk_workspace_model FOREIGN KEY (model_id) REFERENCES model(id),
    ADD CONSTRAINT fk_workspace_latest_job FOREIGN KEY (latest_job_id) REFERENCES training_job(id),
    ADD CONSTRAINT fk_workspace_result FOREIGN KEY (result_job_id) REFERENCES training_job(id);

UPDATE workspace_context
SET model_id=(SELECT id FROM model WHERE is_current=1 ORDER BY id DESC LIMIT 1)
WHERE id='default';
