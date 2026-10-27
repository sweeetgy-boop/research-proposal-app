-- P2-8 표 사실 (2026-10-27): 수집 문서의 표 한 칸 = 한 행. documents 와 FK 를 걸지 않는다 — 적재 순서와
-- 무관하게 쓰고(문서가 나중에 들어와도 doc_id 로 연결), 문서 갱신(upsert) 때 사실이 사라지지 않게.
-- 값은 REAL(비교·정렬)과 적힌 그대로(value_text, "1,512") 둘 다 둔다. basis: text | image_vision.
CREATE TABLE table_facts (
    id          INTEGER PRIMARY KEY,
    doc_id      TEXT NOT NULL,
    item        TEXT NOT NULL,
    year        INTEGER,
    unit        TEXT,
    value       REAL NOT NULL,
    value_text  TEXT NOT NULL,
    page        INTEGER,
    sheet       TEXT,
    row_label   TEXT,
    col_label   TEXT,
    basis       TEXT NOT NULL DEFAULT 'text' CHECK (basis IN ('text', 'image_vision')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX idx_table_facts_doc ON table_facts(doc_id);
CREATE INDEX idx_table_facts_item ON table_facts(item);
