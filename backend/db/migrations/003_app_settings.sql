-- Migration 003: Application settings table
-- Stores configurable runtime settings (logging, Celery concurrency, etc.)

CREATE TABLE IF NOT EXISTS app_settings (
    key         VARCHAR(100) PRIMARY KEY,
    value       TEXT         NOT NULL DEFAULT '',
    description TEXT,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

INSERT INTO app_settings (key, value, description) VALUES
    ('log_level',         'info',                       'Logging level: debug | info | error'),
    ('log_output',        'file',                       'Log destination: file | splunk | both'),
    ('log_dir',           '/app/logs',                  'Directory for log files (container path)'),
    ('splunk_hec_url',    '',                           'Splunk HEC endpoint (e.g. https://splunk:8088/services/collector/event)'),
    ('splunk_hec_token',  '',                           'Splunk HEC authentication token'),
    ('splunk_hec_index',  'media_metrics',              'Splunk index name'),
    ('celery_concurrency','1',                          'Celery worker pool concurrency (processes per worker container)')
ON CONFLICT (key) DO NOTHING;
