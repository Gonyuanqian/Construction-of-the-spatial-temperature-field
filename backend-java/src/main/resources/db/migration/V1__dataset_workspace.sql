-- Only Java-owned dataset and workspace records; existing model rows are untouched.
CREATE TABLE IF NOT EXISTS dataset_record (
    id CHAR(36) NOT NULL PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    storage_key VARCHAR(96) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    legacy_signature VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    n_times INT NOT NULL,
    n_columns INT NOT NULL,
    time_start VARCHAR(48) NOT NULL,
    time_end VARCHAR(48) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_dataset_storage (storage_key),
    KEY idx_dataset_content (content_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS workspace_context (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    dataset_id CHAR(36) NULL,
    revision BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_workspace_dataset FOREIGN KEY (dataset_id) REFERENCES dataset_record(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO workspace_context (id) VALUES ('default');
