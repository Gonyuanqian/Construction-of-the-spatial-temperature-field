-- Keep all existing manual observations. Automatic identities additionally distinguish
-- provider grid, forecast revision and model-profile revision at the same valid time.
ALTER TABLE weather_frame MODIFY COLUMN location_key VARCHAR(80) NOT NULL DEFAULT '';
