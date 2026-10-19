-- Idempotency keys are opaque ASCII values; letter case must remain significant.
ALTER TABLE training_job
    MODIFY request_key VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL;
