-- Step 2 초기 스키마. FTS5(unicode61) + 벡터 테이블은 차원을 알아야 하므로 런타임 생성.

CREATE TABLE documents (
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
    raw_json        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_documents_doi ON documents(doi) WHERE doi IS NOT NULL;
CREATE INDEX idx_documents_appno ON documents(application_no) WHERE application_no IS NOT NULL;
CREATE INDEX idx_documents_department ON documents(department) WHERE department IS NOT NULL;

-- orgs 필터를 인덱스로 태우기 위한 정규화 테이블
CREATE TABLE document_orgs (
    doc_id  TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    org     TEXT NOT NULL,
    PRIMARY KEY (doc_id, org)
) WITHOUT ROWID;

CREATE INDEX idx_document_orgs_org ON document_orgs(org);

CREATE TABLE chunks (
    id        INTEGER PRIMARY KEY,
    chunk_id  TEXT NOT NULL UNIQUE,
    doc_id    TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    ordinal   INTEGER NOT NULL,
    heading   TEXT,
    text      TEXT NOT NULL
);

CREATE INDEX idx_chunks_doc ON chunks(doc_id);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text,
    heading,
    content='chunks',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, heading) VALUES (new.id, new.text, new.heading);
END;

CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, heading)
    VALUES ('delete', old.id, old.text, old.heading);
END;

CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, heading)
    VALUES ('delete', old.id, old.text, old.heading);
    INSERT INTO chunks_fts(rowid, text, heading) VALUES (new.id, new.text, new.heading);
END;

CREATE TABLE meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
