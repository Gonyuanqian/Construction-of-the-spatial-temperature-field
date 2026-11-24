CREATE TABLE greenhouse_design_inspection (
    id CHAR(36) NOT NULL PRIMARY KEY,
    owner_id CHAR(36) NOT NULL,
    design_id CHAR(36) NOT NULL,
    design_revision BIGINT NOT NULL,
    request_key CHAR(36) NOT NULL,
    spec_json LONGTEXT NOT NULL,
    layout_json LONGTEXT NOT NULL,
    assistant_snapshot_id CHAR(36) NULL,
    assistant_run_id CHAR(36) NULL,
    completed_json LONGTEXT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_design_inspection_request (owner_id,request_key),
    KEY idx_design_inspection_history (owner_id,design_id,created_at),
    CONSTRAINT fk_inspection_owner FOREIGN KEY (owner_id) REFERENCES app_user(id),
    CONSTRAINT fk_inspection_design FOREIGN KEY (design_id) REFERENCES greenhouse_design(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
