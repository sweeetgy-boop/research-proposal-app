-- [6] 자료원 상태 (GET /v1/sources/status): 문서별 적재 시각. upsert 때마다 갱신한다.
ALTER TABLE documents ADD COLUMN ingested_at TEXT;
UPDATE documents SET ingested_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE ingested_at IS NULL;
CREATE INDEX idx_documents_ingested ON documents(source, ingested_at);
