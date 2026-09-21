-- Step 5 보강: 본문 근거 수준. full_text=원문 파일, summary=알리오 공개 요약, abstract=초록·과제요약.
-- 청크의 basis 는 문서에서 JOIN 으로 읽는다 (중복 저장하지 않음).

ALTER TABLE documents ADD COLUMN text_basis TEXT NOT NULL DEFAULT 'full_text'
    CHECK (text_basis IN ('full_text', 'summary', 'abstract'));

-- 기존 행: 알리오는 filedrop 원문뿐이었고, 나머지 소스는 초록·과제요약이다.
UPDATE documents SET text_basis = 'abstract' WHERE source <> 'alio';
