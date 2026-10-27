# ADR 0022 — 표 구조화(table_facts)와 용어 후보 추출은 보수적 규칙 + 사람 승인 (2026-10-27)

## 배경
공사 홈페이지 스냅샷(레인 A)에는 통계 xlsx(역별 승강설비·시간대별 승하차·자재단가 …) 59건과 보고서 pdf 69건이 있고,
P3 이미지 판독은 표 이미지를 `structure{cols, rows, units}` 로 돌려준다. 생성 초안의 수치 lint(`unsupported_number`)는
문장이 인용한 **청크 본문**에 같은 값이 있어야 통과하는데, 표의 숫자는 청크에 흩어져 있거나(시트) 아예 적재되지 않아
(xlsx 첨부) 표에서 온 수치가 "지어낸 수치" 로 보인다. 한편 용어사전(`overlap.yaml generic_terms`·철도 용어)은 손으로
채우고 있어 코퍼스가 늘어도 자라지 않는다(architecture §5-7).

## 선택지
1. 표 구조화: (a) LLM 에게 표를 읽혀 JSON 으로 — 비용·환각·검증 문제. (b) 순수 규칙으로 머리글·연도·단위·숫자만 뽑고
   못 읽으면 내지 않는다. (c) 외부 표 추출 라이브러리(camelot 등) — pdf 전용·의존성 큼.
2. 사실의 쓰임: lint 가 (a) 저장소를 lint 시점에 조회 vs (b) retrieve 때 스냅샷에 고정.
3. 문서가 아직 적재되지 않은 첨부(xlsx 는 현재 `ExtractResult.text` 필수라 적재 실패)의 사실을 (a) 버린다 (b) doc_id 로
   저장하고 건수를 보고한다.
4. 용어 후보: (a) 통계만 내고 사람이 반영 (b) 자동으로 overlap.yaml 에 추가.

## 결정
- 1(b): `domain/rules/table_facts.py` — 머리글 행(값 셀 40% 미만), 두 줄 병합 머리글, 연도 열/행 연도, 단위 우선순위
  (셀 접미 > 열 괄호 > 행 괄호 > "(단위: …)" > 어댑터 기본값), 연번·식별자(번호·코드·전화·일자) 열 제외, 긴 문장·날짜
  셀은 라벨 제외. PDF 텍스트는 셀이 줄로 흩어지므로 "위쪽 8줄 안 같은 블록의 연도/라벨 줄과 개수가 맞는 숫자 줄" 만
  (실측: 69개 pdf 에서 2건). 이미지 판독은 `unconfirmed_numbers` 가 있으면 표 통째 제외.
- 2(b): `RetrievalSnapshot.facts`(doc_id → 사실, 문서당 300·전체 2,000, 연도·단위 있는 것 우선). lint 경로가 동기이고
  state.json 을 화면이 2초마다 읽으므로 전부 넣지 않는다. 큰 시트의 나머지는 lint 시점 지연 조회(비동기 lint)로 — 후속.
- 3(b): `table_facts` 는 documents 와 FK 없음. 적재 뒤 돌리는 것이 기본이지만 순서가 바뀌어도 사실이 남고
  `missing_doc` 으로 보인다. 수치 lint 는 검색 집합 문서의 사실만 쓰므로 해가 없다.
- 4(a): `rra terms candidates` 는 `config/rail_terms.candidates.yaml`·`generic_terms.candidates.yaml` 만 쓴다.
  overlap.yaml 반영은 사람(이슈 #11). 후보 분류는 문서빈도(df/문서수 ≥ 0.15 & 자료원 ≥ 2 → 흔한 단어, 나머지 → 철도
  용어 후보, 철도 어근 hint 표시) — 표시일 뿐 조건이 아니다.

## 이유
틀린 사실 하나가 "지어낸 수치" 를 근거 있는 것으로 둔갑시키므로 재현율보다 정밀도. 표본(실물 xlsx 2·pdf 1)과 합성
fixture 만으로 규칙을 정했고, LLM·네트워크 없이 돈다(보안 A·B: 파싱은 샌드박스, 사실은 비신뢰로 표시해 내보낸다).

## 결과
`TableFact`·`ParsedTable`, migration 005, `TableFactRepository`·`TableSourcePort`·`CorpusAccessPort`,
`ExtractTableFacts`·`ExtractTermCandidates`, 어댑터 `adapters/tables/`(SnapshotTables·VisionTables·DocumentTables)·
`adapters/terms/`, `_worker pdf_pages`, `rra facts extract|search`, `rra terms candidates`, `GET /v1/facts`.
scratch DB 측정(레인 A 스냅샷 2026-10-27, 샌드박스 실파싱 59초): 표 2,094장 → 사실 48,253건 / 문서 32건(xlsx·xls 모두
미적재 상태), 사실 없는 표 2,035장(대부분 pdf 쪽), 단위 있는 사실 46%, 연도 있는 사실 23%. 테스트 1,572 통과·계약 8 유지.
