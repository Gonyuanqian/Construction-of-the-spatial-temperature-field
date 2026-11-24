CREATE TABLE prototype_weather_frame (
    id CHAR(36) NOT NULL PRIMARY KEY,
    created_by CHAR(36) NOT NULL,
    query_id CHAR(36) NOT NULL,
    reference_id CHAR(64) NOT NULL,
    geometry_sha256 CHAR(64) NOT NULL,
    dimensions_json LONGTEXT NOT NULL,
    source_json LONGTEXT NOT NULL,
    location_json LONGTEXT NOT NULL,
    observed_at TIMESTAMP(6) NOT NULL,
    bg_temp DOUBLE NOT NULL,
    bg_rh DOUBLE NULL,
    bg_light DOUBLE NOT NULL,
    summary_json LONGTEXT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_prototype_query (created_by,query_id,reference_id,geometry_sha256),
    KEY idx_prototype_owner_time (created_by,created_at),
    CONSTRAINT fk_prototype_user FOREIGN KEY (created_by) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
