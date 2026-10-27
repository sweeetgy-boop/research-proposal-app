# ADR 0016 — 특허 기본 자료원은 ScienceON PATENT, KIPRIS 는 선택 (2026-10-27, 레인 B feat/scienceon-live)

**배경** 기획서 기능 3·4(선행기술·차별성)에 국내 특허가 필요하다. KIPRIS Plus 어댑터는 코드만 있고 키·실응답이 없다(P4).
ScienceON 실연결 과정에서 같은 키로 `target=PATENT` 가 열려 있음을 확인했다.

**선택지** (a) KIPRIS 를 기본으로 두고 키를 기다린다, (b) ScienceON PATENT 를 기본으로 하고 KIPRIS 는 키 확보 뒤 보강, (c) 둘 다 기본.

**결정** (b).

**이유**
- 건수: "철도 궤도" 911건, "전차선" 1,173건, "철도 신호" 1,465건 — 선행기술 근거로 충분한 폭(13개 질의 합 ≈ 3,700건, 질의당 상한 전).
- 필드: Title·Abstract·Applicants(출원인)·ApplNum·ApplDate·PublDate·GrantDate·IPC·PatentStatus·Nation·ContentURL. 제안서가 쓰는
  제목·초록·출원 기관·출원번호·일자·IPC 가 모두 있다. **발명자(IN)는 검색 필드일 뿐 출력 항목에 없어** 사람 이름 제거 부담이 없다
  (출원인은 `is_organization` 으로 기관만 남긴다 — KIPRIS 와 같은 규칙).
- 운영: 키·MAC·레이트리밋(1 req/s, run 예산)·토큰 관리가 논문·보고서와 하나라 야간 적재(`--skip-unavailable`)에 그대로 들어간다.
- 한계: 한국 특허(KOR CN, DBCode KUPA·KPTN·KUUM·KUMO·KPAT)만 확인했고 청구항·등록 상세·해외 특허는 없다. KIPRIS 는 그 상세가
  필요해질 때 키를 받아 보강한다(`kipris_kr` 문서 id 는 출원번호, ScienceON 은 CN 이라 충돌 없음 — 같은 특허가 두 번 들어올 수
  있으니 합칠 때 `application_no` 로 중복 제거).

**결과** `sources.yaml scienceon.targets: [ARTI, REPORT, PATENT]`, `normalize.py` 가 PATENT → `doc_type=patent`,
`application_no`·`codes(IPC)`·`raw.status`. fixture `scienceon_PATENT_20261027_1.xml`. `docs/external-apis.md` ScienceON 행 갱신.
KIPRIS 행은 "선택(키 확보 뒤)" 로 통합 세션이 바꾼다.
