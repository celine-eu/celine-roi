CREATE TABLE IF NOT EXISTS estimates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint      VARCHAR(20) NOT NULL,
    status        VARCHAR(10) NOT NULL,
    request       JSONB NOT NULL,
    response      JSONB,
    error_message TEXT,
    duration_ms   INTEGER,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_estimates_created_at ON estimates (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_estimates_endpoint ON estimates (endpoint);
