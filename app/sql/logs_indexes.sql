CREATE INDEX IF NOT EXISTS ix_logs_created_at ON logs (created_at);
CREATE INDEX IF NOT EXISTS ix_logs_ip_created ON logs (ip_address, created_at);
