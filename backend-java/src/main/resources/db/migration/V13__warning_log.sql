CREATE TABLE warning_temperature_settings (
    owner_id CHAR(36) NOT NULL PRIMARY KEY,
    low_limit DOUBLE NULL,
    high_limit DOUBLE NULL,
    FOREIGN KEY (owner_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE warning_temperature_cursor (
    owner_id CHAR(36) NOT NULL,
    scope_key CHAR(64) NOT NULL,
    observed_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (owner_id, scope_key),
    FOREIGN KEY (owner_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE warning_temperature_event (
    id CHAR(36) NOT NULL PRIMARY KEY,
    owner_id CHAR(36) NOT NULL,
    scope_key CHAR(64) NOT NULL,
    design_id CHAR(36) NULL,
    greenhouse_name VARCHAR(120) NOT NULL,
    alert_type VARCHAR(8) NOT NULL,
    trigger_frame_id CHAR(36) NOT NULL,
    triggered_at TIMESTAMP(6) NOT NULL,
    last_seen_at TIMESTAMP(6) NOT NULL,
    threshold_value DOUBLE NOT NULL,
    trigger_value DOUBLE NOT NULL,
    extreme_value DOUBLE NOT NULL,
    ended_at TIMESTAMP(6) NULL,
    end_reason VARCHAR(16) NULL,
    KEY idx_temperature_warning_history (owner_id, triggered_at),
    KEY idx_temperature_warning_open (owner_id, scope_key, alert_type, ended_at),
    FOREIGN KEY (owner_id) REFERENCES app_user(id),
    FOREIGN KEY (design_id) REFERENCES greenhouse_design(id),
    FOREIGN KEY (trigger_frame_id) REFERENCES prototype_weather_frame(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE warning_acknowledgement (
    owner_id CHAR(36) NOT NULL,
    category VARCHAR(12) NOT NULL,
    event_id CHAR(36) NOT NULL,
    acknowledged_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    acknowledged_by VARCHAR(120) NOT NULL,
    PRIMARY KEY (owner_id, category, event_id),
    FOREIGN KEY (owner_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
