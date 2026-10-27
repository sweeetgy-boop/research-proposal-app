-- 006 (2026-10-27): documents.text_basis CHECK 에 'image_vision' 추가.
-- 도메인 TextBasis 는 image_vision(웹 페이지 이미지 판독)을 허용하지만 002 의 CHECK 가 그대로여서
-- `rra vision ingest` 의 upsert 가 CHECK constraint failed 로 실패했다.
-- SQLite 는 CHECK 를 ALTER 로 못 바꾸므로 공식 12단계 절차대로 표를 재생성한다:
-- FK 끄기 → 새 표 → INSERT SELECT(rowid 보존) → DROP → RENAME → 인덱스 복원 → FK 켜기.
-- documents 에는 트리거가 없고 FTS 는 chunks 에만 걸려 있다. chunks·document_orgs 의
-- `REFERENCES documents(doc_id)` 는 이름으로 묶이므로 RENAME 뒤 새 표를 가리킨다.
-- PRAGMA foreign_keys 는 트랜잭션 밖에서만 듣는다 — BEGIN 앞·COMMIT 뒤에 둔다. FK 를 끄지 않으면
-- DROP TABLE 이 암묵적 DELETE 로 chunks·document_orgs 를 ON DELETE CASCADE 로 지운다.

PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE documents_new (
    doc_id          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    doc_type        TEXT NOT NULL,
    title           TEXT NOT NULL,
    abstract        TEXT,
    body            TEXT,
    pub_date        TEXT,
    lang            TEXT NOT NULL DEFAULT 'ko',
    url             TEXT,
    doi             TEXT,
    application_no  TEXT,
    department      TEXT,
    period_start    TEXT,
    period_end      TEXT,
    authors_json    TEXT NOT NULL DEFAULT '[]',
    codes_json      TEXT NOT NULL DEFAULT '[]',
    orgs_json       TEXT NOT NULL DEFAULT '[]',
    toc_json        TEXT,
    raw_json        TEXT NOT NULL DEFAULT '{}',
    -- 002: 본문 근거 수준 (+ image_vision)
    text_basis      TEXT NOT NULL DEFAULT 'full_text'
        CHECK (text_basis IN ('full_text', 'summary', 'abstract', 'image_vision')),
    -- 003: 유효기간·공개범위
    valid_until     TEXT,
    visibility      TEXT NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('public', 'internal')),
    -- 004: 적재 시각
    ingested_at     TEXT
);

INSERT INTO documents_new (
    rowid, doc_id, source, doc_type, title, abstract, body, pub_date, lang, url, doi,
    application_no, department, period_start, period_end, authors_json, codes_json, orgs_json,
    toc_json, raw_json, text_basis, valid_until, visibility, ingested_at
)
SELECT
    rowid, doc_id, source, doc_type, title, abstract, body, pub_date, lang, url, doi,
    application_no, department, period_start, period_end, authors_json, codes_json, orgs_json,
    toc_json, raw_json, text_basis, valid_until, visibility, ingested_at
FROM documents;

DROP TABLE documents;
ALTER TABLE documents_new RENAME TO documents;

-- 001·003·004 의 인덱스 복원
CREATE INDEX idx_documents_doi ON documents(doi) WHERE doi IS NOT NULL;
CREATE INDEX idx_documents_appno ON documents(application_no) WHERE application_no IS NOT NULL;
CREATE INDEX idx_documents_department ON documents(department) WHERE department IS NOT NULL;
CREATE INDEX idx_documents_valid_until ON documents(valid_until) WHERE valid_until IS NOT NULL;
CREATE INDEX idx_documents_ingested ON documents(source, ingested_at);

COMMIT;

PRAGMA foreign_keys = ON;
