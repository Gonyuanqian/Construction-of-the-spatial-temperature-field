CREATE TABLE app_user (
    id CHAR(36) NOT NULL PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    password_hash VARCHAR(100) NOT NULL,
    role VARCHAR(16) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auth_version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_user_username (username),
    CONSTRAINT ck_user_role CHECK (role IN ('ADMIN','USER'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE auth_session (
    token_hash CHAR(64) NOT NULL PRIMARY KEY,
    user_id CHAR(36) NOT NULL,
    auth_version BIGINT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at TIMESTAMP(6) NOT NULL,
    KEY idx_session_user (user_id),
    KEY idx_session_expiry (expires_at),
    CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Serializes administrative account mutations, including last-admin protection.
CREATE TABLE user_admin_lock (id INT NOT NULL PRIMARY KEY);
INSERT INTO user_admin_lock (id) VALUES (1);

CREATE TABLE weather_model (
    id CHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    model_id BIGINT NOT NULL,
    package_id CHAR(36) NOT NULL,
    package_sha256 CHAR(64) NOT NULL,
    external_schema VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    metadata_json LONGTEXT NOT NULL,
    created_by CHAR(36) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_weather_package (package_id),
    CONSTRAINT fk_weather_model FOREIGN KEY (model_id) REFERENCES model(id),
    CONSTRAINT fk_weather_creator FOREIGN KEY (created_by) REFERENCES app_user(id),
    CONSTRAINT ck_weather_schema CHECK (external_schema IN ('two','full')),
    CONSTRAINT ck_weather_status CHECK (status IN ('DRAFT','PUBLISHED','DISABLED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse (
    id CHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    location_text VARCHAR(255) NOT NULL DEFAULT '',
    geometry_key VARCHAR(40) NOT NULL DEFAULT 'ginseng_arch_v1',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    weather_model_id CHAR(36) NULL,
    revision BIGINT NOT NULL DEFAULT 0,
    created_by CHAR(36) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_greenhouse_model FOREIGN KEY (weather_model_id) REFERENCES weather_model(id),
    CONSTRAINT fk_greenhouse_creator FOREIGN KEY (created_by) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse_member (
    greenhouse_id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    PRIMARY KEY (greenhouse_id,user_id),
    CONSTRAINT fk_member_greenhouse FOREIGN KEY (greenhouse_id) REFERENCES greenhouse(id),
    CONSTRAINT fk_member_user FOREIGN KEY (user_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE weather_frame (
    id CHAR(36) NOT NULL PRIMARY KEY,
    greenhouse_id CHAR(36) NOT NULL,
    weather_model_id CHAR(36) NOT NULL,
    observed_at TIMESTAMP(6) NOT NULL,
    bg_temp DOUBLE NOT NULL,
    bg_light DOUBLE NOT NULL,
    bg_rh DOUBLE NULL,
    input_sha256 CHAR(64) NOT NULL,
    summary_json LONGTEXT NOT NULL,
    created_by CHAR(36) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_weather_frame_time (greenhouse_id,observed_at),
    KEY idx_weather_frame_house (greenhouse_id,observed_at),
    CONSTRAINT fk_frame_greenhouse FOREIGN KEY (greenhouse_id) REFERENCES greenhouse(id),
    CONSTRAINT fk_frame_weather_model FOREIGN KEY (weather_model_id) REFERENCES weather_model(id),
    CONSTRAINT fk_frame_user FOREIGN KEY (created_by) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
