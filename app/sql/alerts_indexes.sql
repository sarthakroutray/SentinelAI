CREATE INDEX IF NOT EXISTS ix_alerts_created_at ON alerts (created_at);
CREATE INDEX IF NOT EXISTS ix_alerts_risk_score ON alerts (risk_score);
CREATE INDEX IF NOT EXISTS ix_alerts_severity_created_at ON alerts (severity, created_at);
