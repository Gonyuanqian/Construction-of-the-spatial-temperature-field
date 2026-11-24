-- Shared, geographically matched archives replace per-user greenhouse grants.
-- Existing rows remain visible to administrators until their archive is completed.
ALTER TABLE greenhouse
    ADD COLUMN province_code CHAR(6) NULL,
    ADD COLUMN city_code CHAR(6) NULL,
    ADD COLUMN district_code CHAR(6) NULL,
    ADD COLUMN length_m DOUBLE NULL,
    ADD COLUMN width_m DOUBLE NULL,
    ADD COLUMN height_m DOUBLE NULL,
    ADD COLUMN active_region CHAR(6) GENERATED ALWAYS AS
        (CASE WHEN enabled=TRUE AND city_code IS NOT NULL THEN COALESCE(district_code,city_code) ELSE NULL END) STORED,
    ADD UNIQUE KEY uq_greenhouse_active_region (active_region),
    ADD KEY idx_greenhouse_region (city_code,district_code);

CREATE TABLE greenhouse_catalog_lock (id INT NOT NULL PRIMARY KEY);
INSERT INTO greenhouse_catalog_lock (id) VALUES (1);

-- A shared archive must never make different users share weather history.
ALTER TABLE weather_frame
    DROP INDEX uq_weather_frame_time,
    ADD COLUMN location_key CHAR(6) NOT NULL DEFAULT '',
    ADD UNIQUE KEY uq_weather_frame_owner_time (created_by,greenhouse_id,location_key,observed_at),
    ADD COLUMN location_json TEXT NULL,
    ADD COLUMN archive_snapshot_json LONGTEXT NULL;

-- greenhouse_member is retained as legacy data only; no application API uses it.
