CREATE TABLE greenhouse_design (
    id CHAR(36) NOT NULL PRIMARY KEY,
    owner_id CHAR(36) NOT NULL,
    name VARCHAR(120) NOT NULL,
    revision BIGINT NOT NULL DEFAULT 1,
    spec_json LONGTEXT NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_design_owner (owner_id, updated_at),
    CONSTRAINT fk_design_owner FOREIGN KEY (owner_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE greenhouse_design_selection (
    owner_id CHAR(36) NOT NULL PRIMARY KEY,
    design_id CHAR(36) NOT NULL,
    design_revision BIGINT NOT NULL,
    snapshot_json LONGTEXT NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_design_selection_owner FOREIGN KEY (owner_id) REFERENCES app_user(id),
    CONSTRAINT fk_design_selection_design FOREIGN KEY (design_id) REFERENCES greenhouse_design(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
