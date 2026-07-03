-- BlueLotus V3 Database Bloat Reduction Schema
-- Append-only, hash-addressed object store. Non-destructive.

CREATE TABLE IF NOT EXISTS institutional_object_store (
  object_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  object_type VARCHAR(64) NOT NULL,
  object_hash CHAR(64) NOT NULL,
  object_version VARCHAR(64),
  payload_json JSON NOT NULL,
  payload_size_bytes BIGINT NOT NULL,
  source_system VARCHAR(64),
  schema_version VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_institutional_object_hash (object_hash),
  KEY idx_institutional_object_type (object_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS institutional_object_references (
  reference_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  cycle_id VARCHAR(128) NOT NULL,
  object_type VARCHAR(64) NOT NULL,
  object_hash CHAR(64) NOT NULL,
  payload_size_bytes BIGINT NOT NULL,
  source_system VARCHAR(64),
  schema_version VARCHAR(64),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  KEY idx_object_ref_cycle (cycle_id),
  KEY idx_object_ref_hash (object_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS v3_cycle_manifests (
  manifest_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  cycle_id VARCHAR(128) NOT NULL,
  dataset_hash CHAR(64) NOT NULL,
  dataset_payload_size_bytes BIGINT NOT NULL,
  manifest_json JSON NOT NULL,
  execution_authority VARCHAR(64) NOT NULL DEFAULT 'CIO_ONLY_MANUAL',
  order_routing_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  system_orders_generated INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_v3_cycle_manifest_hash (dataset_hash),
  KEY idx_v3_cycle_manifest_cycle (cycle_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

