-- [2] DB 정비 (2026-10-26): 적용 이력 표, 문서 유효기간·공개범위.
-- schema_version: PRAGMA user_version 과 함께 적용 시각을 남긴다 (runner 가 행을 넣는다).
CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- valid_until: 이 날짜(ISO, 포함)까지만 검색·precheck 대상. NULL 이면 만료 없음.
ALTER TABLE documents ADD COLUMN valid_until TEXT;
-- visibility: public=외부(검토 LLM 등)에 보낼 수 있는 자료, internal=사내 전용.
ALTER TABLE documents ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'
    CHECK (visibility IN ('public', 'internal'));

CREATE INDEX idx_documents_valid_until ON documents(valid_until) WHERE valid_until IS NOT NULL;
