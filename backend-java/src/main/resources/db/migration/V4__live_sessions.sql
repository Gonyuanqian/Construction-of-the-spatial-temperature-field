CREATE TABLE live_session (
    id CHAR(36) NOT NULL PRIMARY KEY,
    request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    expected_session_id CHAR(36) NULL,
    model_id BIGINT NOT NULL,
    state VARCHAR(20) NOT NULL DEFAULT 'preparing',
    is_pending TINYINT(1) NOT NULL DEFAULT 1,
    pending_slot TINYINT GENERATED ALWAYS AS (CASE WHEN is_pending=1 THEN 1 ELSE NULL END) STORED,
    source_manifest LONGTEXT NULL,
    `cursor` INT NOT NULL DEFAULT 0,
    total INT NOT NULL DEFAULT 0,
    running TINYINT(1) NOT NULL DEFAULT 0,
    interval_s DOUBLE NOT NULL DEFAULT 300,
    python_instance_id CHAR(36) NULL,
    last_error TEXT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_live_request (request_key),
    UNIQUE KEY uq_live_preparing (pending_slot),
    CONSTRAINT fk_live_model FOREIGN KEY (model_id) REFERENCES model(id),
    CONSTRAINT ck_live_state CHECK (state IN ('preparing','ready','needs_restore','failed')),
    CONSTRAINT ck_live_cursor CHECK (`cursor`>=0 AND total>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE live_operation (
    id CHAR(36) NOT NULL PRIMARY KEY,
    session_id CHAR(36) NOT NULL,
    request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
    action VARCHAR(16) NOT NULL,
    from_n INT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'pending',
    pending_slot TINYINT GENERATED ALWAYS AS (CASE WHEN state='pending' THEN 1 ELSE NULL END) STORED,
    python_instance_id CHAR(36) NOT NULL,
    response_json LONGTEXT NULL,
    error TEXT NULL,
    error_status INT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_live_operation_key (session_id,request_key),
    UNIQUE KEY uq_live_operation_pending (session_id,pending_slot),
    CONSTRAINT fk_operation_live FOREIGN KEY (session_id) REFERENCES live_session(id),
    CONSTRAINT ck_live_operation_state CHECK (state IN ('pending','done','failed')),
    CONSTRAINT ck_live_operation_action CHECK (action IN ('start','pause','next'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE workspace_context
    ADD COLUMN live_session_id CHAR(36) NULL,
    ADD CONSTRAINT fk_workspace_live FOREIGN KEY (live_session_id) REFERENCES live_session(id);
