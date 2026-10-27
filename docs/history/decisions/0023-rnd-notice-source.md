# ADR 0023 — 정부 R&D 공고(rnd_notice) 수집처·쓰임 범위 (2026-10-27, P2-7)

## 배경
연구과제 공고문 반영(#13)은 사용자가 `data/inbox/notice/` 에 파일을 넣기를 기다리고 있었다. 국토교통 분야 정부 R&D 공고는
KAIA·IRIS·NTIS 에 공개돼 있어 접수 중인 공고를 입력과 대조해 보여 주고, 공고문 텍스트를 정책 근거 추천 후보로 쓸 수 있다.

## 선택지
1. 수집처: KAIA 사업공고(GET, robots Allow) / IRIS 사업공고(JS 템플릿 + 공개 POST 검색 폼, robots 허용) / NTIS 공고(robots
   `Disallow: /`) / 공공데이터포털 API(국토교통 R&D 공고 API 없음, 타 부처는 키 필요).
2. IRIS 첨부(세션 POST 다운로드)를 흉내 내서 받을지, 이름만 기록할지.
3. 같은 공고가 두 사이트에 있을 때 두 문서로 둘지 한 문서로 합칠지.
4. `rnd_notice` 를 유사과제 판정·기술적 중요도 근거에 쓸지.

## 결정
- 1: KAIA 를 주 수집처(PDF 공고문·안내서 첨부), IRIS 를 국토교통부 필터 보조 수집처(공고문 본문 인라인)로 쓴다. 공개 POST 검색
  폼은 robots 가 그 경로를 금지하지 않고 로그인·세션이 없어 허용 규칙(자동 판단)대로 쓴다. NTIS 는 robots 전면 금지라 공개
  페이지를 수집하지 않는다(키 API 만, 공고 API 유무는 키 뒤 확인). 둘 다 `allowed_domains` 에 추가, GuardedClient 2초 간격·동시 1,
  403/429 백오프 2→5→10s·연속 3회 보류·끝에 1회 재시도.
- 2: 이름만 기록한다(`post_download`). 봇 보호·세션 흐름을 흉내 내지 않는다. RFP 텍스트는 인라인 공고문으로 확보되고, 같은 공고가
  KAIA 에 있으면 PDF 가 붙는다.
- 3: 한 문서로 합친다 — `domain/rules/notices.notice_key`(정규화 제목+기관+공고일 해시). 나머지 URL 은 `raw.notice.also_in`.
- 4: 쓰지 않는다. `retrieval_scope.OVERLAP_EXCLUDED_DOC_TYPES`·`NON_OVERLAP_SOURCES` 에 넣고(retrieval_mix.yaml `overlap_exclude`
  에도 이미 있음), 정책 근거 추천(`POLICY_DOC_TYPES`·`POLICY_SOURCES`)과 공고문 대조(`usecases/notice_match`, 접수 중 상위 3건,
  LLM 없음, 자동 삽입 없음)에만 쓴다. `valid_until` = 접수 마감일이라 마감 지난 공고는 저장소 규칙으로 검색·precheck 에서 빠진다.
- 담당자 이름·전화·이메일은 저장 전 `strip_pii` 로 지운다(IRIS 상세의 사업담당자 칸은 아예 기록하지 않음). 스냅샷·첨부는 커밋하지
  않는다(`data/`).

## 영향
- 새 SourceType·DocType `rnd_notice`, `config/rnd_notice.yaml`, `rra crawl rnd-notice`, `rra ingest --source rnd_notice`,
  `rra notices match`, `POST /v1/ideas/notices`, `GET /v1/sources/status` 의 `rnd_notice` 행(스냅샷 라벨).
- #13 은 그대로 열어 둔다 — 이 공고 목록은 "어느 공고에 낼지" 를 고르는 선행 단계이고, 공고 요건(기간·예산·양식) 추출·render_check
  대조는 #13 에서 이어진다(`notice_id` 는 `rnd_notice:<key>` 로 이어 쓸 수 있다).
