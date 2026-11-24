-- Personal, simulated device control. No physical actuator connection is implied.
CREATE TABLE greenhouse_control (
    design_id CHAR(36) NOT NULL PRIMARY KEY,
    owner_id CHAR(36) NOT NULL,
    design_revision BIGINT NOT NULL,
    spec_json LONGTEXT NOT NULL,
    epoch BIGINT NOT NULL DEFAULT 1,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_control_design FOREIGN KEY (design_id) REFERENCES greenhouse_design(id),
    CONSTRAINT fk_control_owner FOREIGN KEY (owner_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse_control_device (
    id CHAR(36) NOT NULL PRIMARY KEY,
    design_id CHAR(36) NOT NULL,
    name VARCHAR(80) NOT NULL,
    kind VARCHAR(20) NOT NULL,
    zone_key VARCHAR(20) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    revision BIGINT NOT NULL DEFAULT 1,
    state_json LONGTEXT NOT NULL,
    stop_at TIMESTAMP(6) NULL,
    runtime_seconds BIGINT NOT NULL DEFAULT 0,
    runtime_day DATE NULL,
    day_runtime_seconds BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_control_device_house FOREIGN KEY (design_id) REFERENCES greenhouse_control(design_id),
    CONSTRAINT ck_control_device_kind CHECK (kind IN ('drip','sprinkler','ventilation','lighting')),
    CONSTRAINT ck_control_device_zone CHECK (zone_key IN ('all','a','b'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse_control_task (
    id CHAR(36) NOT NULL PRIMARY KEY,
    design_id CHAR(36) NOT NULL,
    device_id CHAR(36) NOT NULL,
    name VARCHAR(100) NOT NULL,
    source VARCHAR(20) NOT NULL,
    plan_id CHAR(36) NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL,
    status VARCHAR(20) NOT NULL,
    spec_json LONGTEXT NOT NULL,
    next_run_at TIMESTAMP(6) NULL,
    last_run_at TIMESTAMP(6) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_control_task_due (enabled,next_run_at),
    CONSTRAINT fk_control_task_house FOREIGN KEY (design_id) REFERENCES greenhouse_control(design_id),
    CONSTRAINT fk_control_task_device FOREIGN KEY (device_id) REFERENCES greenhouse_control_device(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse_control_event (
    id CHAR(36) NOT NULL PRIMARY KEY,
    design_id CHAR(36) NOT NULL,
    device_id CHAR(36) NULL,
    request_key CHAR(36) NOT NULL,
    fingerprint LONGTEXT NOT NULL,
    source VARCHAR(20) NOT NULL,
    operation VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    result_json LONGTEXT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_control_request (design_id,request_key),
    KEY idx_control_events (design_id,created_at),
    CONSTRAINT fk_control_event_house FOREIGN KEY (design_id) REFERENCES greenhouse_control(design_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse_control_plan (
    id CHAR(36) NOT NULL PRIMARY KEY,
    design_id CHAR(36) NOT NULL,
    request_key CHAR(36) NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL,
    input_json LONGTEXT NOT NULL,
    snapshot_json LONGTEXT NOT NULL,
    result_json LONGTEXT NULL,
    confirmation_json LONGTEXT NULL,
    error_code VARCHAR(40) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at TIMESTAMP(6) NOT NULL,
    lease_until TIMESTAMP(6) NULL,
    UNIQUE KEY uq_control_plan_request (design_id,request_key),
    KEY idx_control_plan_queue (status,created_at),
    CONSTRAINT fk_control_plan_house FOREIGN KEY (design_id) REFERENCES greenhouse_control(design_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
