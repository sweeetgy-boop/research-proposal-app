# feat/ui-studio-search — 위쪽 통합 검색(⌘K / Ctrl+K)·자료 검색 전체 결과·자료 현황 새 모양 (2026-10-29, [UI] 레인 3)

## 바뀐 것
- **통합 검색** `web/src/features/globalsearch/GlobalSearch.tsx` (`GlobalSearch({className?})`): 돋보기 + "제안서·자료 검색" 입력칸 + ⌘K(맥)/Ctrl K 표시.
  ⌘K·Ctrl+K 로 어디서든 연다. 입력하는 대로(0.25초 뒤) 두 묶음 — "내 제안서" 최대 5건(제목 일치, 공백·대소문자 무시, 최근 수정 순;
  빈 검색어면 "최근 제안서" 3건), "자료" 상위 5건(제목 · 자료원 이름 · 연도, 실시간 검색 배지). 맨 아래 [자료 전체 결과 보기].
  - 제안서 → 그 제안서의 현재 단계 화면(drafted ③ 초안, editing ④ 직접 수정, final_reviewing/final_reviewed ⑤ 최종 검토, finalized ⑥, 그 밖은 진행).
  - 자료 → 근거 패널(`DocRefPanel`: 요약 발췌·원문 링크, 사내 전용은 링크 없음). 패널을 닫으면 입력칸으로 포커스가 돌아온다.
  - [자료 전체 결과 보기], 또는 선택 없이 Enter → `/search?q=…`.
  - 키보드: ↑/↓ 두 묶음과 전체 결과를 돈다, Home/End, Enter 열기, Esc 닫기(포커스는 입력칸, 글자는 남김). ARIA 1.2 combobox + listbox(group 2 + option),
    `aria-activedescendant`, 결과 건수는 화면 읽기용 `role=status` 로 알린다. 바깥 클릭으로 닫힘. 좁은 화면은 팝업이 입력칸 폭 그대로 아래에 열린다.
  - 빈 결과·오류는 묶음마다 이유: "아직 만든 제안서가 없습니다." / "제목이 맞는 제안서가 없습니다." / "맞는 자료가 없습니다. 다른 낱말로 찾아보십시오." /
    "자료를 불러오지 못했습니다: <서버 사유>"(제안서 묶음은 그대로).
  - 로그인 전: 결과를 부르지 않고 로그인으로 보낸다(지금은 `/login` + `state.from`, 레인 1 의 화면 안 로그인 창이 들어오면 `useOpenLogin` 한 곳만 바꾼다).
  - 임시 자리: 지금 `Layout.tsx` 위쪽 메뉴에 한 줄로 붙였다. 레인 1 이 새 위쪽 막대로 옮긴다.
- **API** `GET /v1/search/docs?q=&limit=(1~30, 기본 5)&sources=a,b&year_from=&year_to=` (`entrypoints/api/search_routes.py`,
  `application/usecases/search_documents.py`, `domain/rules/doc_search.py`, 직렬화 `views_refs.doc_hits_payload`): 청크 검색 → 문서별 첫 청크 →
  문서 조회 → 연도 거르기. 응답 `{notice, docs: [{doc_id, title, source, source_label, url, year, summary, basis, live, trust}]}` — 표시 정보만,
  요약은 맞은 청크 발췌 300자. 공용 계정은 `PublicOnlyRepository`(청크 표시 + 문서 조회 두 번 막음)라 internal 이 나오지 않는다. 사내 전용 문서는 url 없음.
  질의가 문서 번호 하나(`openalex:…`)면 그 문서(근거 패널 [원본 보기] 가 `/search?q=<문서 번호>` 로 연다). 모르는 자료원·시작>끝 연도는 422.
- **자료 검색**(`routes/Search.tsx`): 주소가 상태(`q`·`sources`·`year_from`·`year_to`) — 뒤로 가기·공유 그대로. 왼쪽 조건 카드(검색어, 자료원 체크 —
  적재된 자료원만 건수와 함께, 발행 연도 시작~끝, [조건 지우기]), 오른쪽 결과 카드(건수 알약, 문서 한 줄: 자료원·연도·본문 종류·비신뢰 배지,
  제목 버튼 → 근거 패널, 발췌 3줄, 원문 링크). 문서 번호로 열면 번호는 입력칸에도 보이지 않는다. 결과 없음은 "자료원·연도 조건을 넓히거나…".
  예전 청크 단위 결과(유사도 숫자)는 문서 단위로 바뀌었다. 기존 `GET /v1/search`(청크)는 그대로(MCP·다른 화면용).
- **자료 현황**(`routes/Sources.tsx`, 제목 "자료원 상태" → "자료 현황"): 요약 카드 3개(전체 자료 건수·자료가 있는 자료원 n/전체·호출이 거부된 자료원),
  표(자료원 한국어 이름·건수 오른쪽 정렬·마지막 적재). 자료원 영어 키(예: scienceon)는 더 보이지 않는다. 호출 거부 안내 상자는 살구색.
- 디자인 토큰(레인 4, #101): `Eyebrow`(LIBRARY·SOURCES), `shadow-card`·`shadow-pop`, `bg-primary-soft`·`bg-mint`·`bg-apricot`.

## 판단
| 항목 | 판단 | 이유 |
|---|---|---|
| 자료 묶음 데이터 | 새 `GET /v1/search/docs` | 기존 `/v1/search` 는 청크(본문·doc_id)만 — 제목·연도·원문 링크가 없다. 같은 문서 청크가 여러 줄로 나온다 |
| 로직 위치 | usecase(`SearchDocuments`) + 순수 규칙(`doc_search`) | 진입점은 로직 없음 규칙. 저장소는 `_svc(request, "repo")` 로 받아 공용 계정 제외가 그대로 |
| 연도 모르는 자료 | 연도 거르기를 켜면 뺀다 | "2020~2026" 을 골랐는데 연도 없는 자료가 섞이면 거르기를 믿을 수 없다. 화면에 한 줄 안내 |
| 제안서 묶음 | 기존 `GET /v1/runs?limit=50` 을 화면에서 거른다 | 새 API 없이 같은 캐시(`keys.runs`). 소유자 격리는 서버 그대로 |
| 현재 단계 | 상태 → 단계 화면 표 | runStepTargets 는 "열 수 있는 단계" 라 drafted 도 ⑤ 가 된다. 사람이 하던 단계로 보낸다 |
| 디바운스 | 0.25초 | 글자마다 검색하지 않게(vitest 로 1회 호출 확인) |
| 안내 줄 문구 | "비신뢰" 낱말을 쓰지 않음 | 닫힌 팝업 안 글이 기존 e2e `getByText("비신뢰").first()` 와 겹쳤다 |
| 문서 번호 질의 | 그 문서 하나 + 입력칸 비움 | 근거 패널 [원본 보기] 링크가 번호로 연다 — 번호를 화면에 보이지 않으면서 링크를 살린다 |
| 자료 현황 제목 | "자료 현황" | 소유자 지시(사이드바 아래 작은 메뉴 이름). 위쪽 메뉴 링크 이름 "자료원 상태" 는 레인 1 이 바꾼다 |

## ADR 초안 (레인 5 가 0048 이상 번호로 기록)
- 제목: 위쪽 통합 검색과 문서 단위 검색 API
- 맥락: Research Studio 화면은 "자료 검색" 메뉴를 없애고 위쪽 검색창 하나로 내 제안서와 수집 자료를 함께 찾는다. 기존 `/v1/search` 는 청크 단위라
  제목·자료원·연도·원문 링크를 보일 수 없고, 같은 문서가 여러 줄로 나온다. 공용 계정은 internal 자료를 보면 안 된다.
- 결정: `GET /v1/search/docs` 를 더한다 — 청크 검색 → 문서별 첫 청크 → 문서 조회 → 자료원·연도 거르기 → 표시 정보만(doc_id 는 키, 화면에 안 보임).
  저장소는 세션별 서비스(`_svc`)로 받아 공용 계정은 `PublicOnlyRepository` 를 지난다. 화면은 combobox/listbox 하나에 "내 제안서"(기존 runs 목록 거르기)와
  "자료"(새 API 상위 5) 두 묶음, [자료 전체 결과 보기] 는 주소가 상태인 자료 검색 화면(자료원·연도 거르기)을 연다.
- 결과: 검색 화면이 문서 단위가 된다(유사도 숫자는 보이지 않음). 청크 API 는 MCP·기존 쓰임을 위해 남긴다. 자료원 거르기는 저장소 `sources` 필터,
  연도 거르기는 문서 발행 연도로 해서 연도 모르는 자료는 빠진다. 요청 수는 디바운스 0.25초.

## 기록 한 줄
- timeline: `2026-10-29 | [UI] 레인 3 | 위쪽 통합 검색(⌘K/Ctrl+K, 내 제안서·자료 두 묶음, 키보드)·GET /v1/search/docs·자료 검색 자료원·연도 거르기·자료 현황 새 모양 | PR #?`
- metrics.csv: `2026-10-29,<commit>,ui-studio-search,,,,,,,,,,,,,,,,,,"통합 검색·/v1/search/docs, pytest 새 8, vitest 새 15, e2e 새 4"`

## 캡처
- `docs/history/screens/2026-10-29-ui-studio-search-before.png` / `-after.png` (자료 검색)
- `docs/history/screens/2026-10-29-ui-studio-sources-before.png` / `-after.png` (자료 현황)
- `docs/history/screens/2026-10-29-ui-studio-globalsearch-after.png` (통합 검색 팝업, 두 묶음)
