## [W] 웹 ② NTIS 과제 카드 — 주요 성과(참고용)·NTIS 추천 (feat/web-ntis, 2026-10-27)

- 기준: main bcdbf16(PR #35 NTIS 실연결, ADR 0020). 백엔드 `POST /v1/precheck/ntis-outcomes` 는 그대로 쓰고 화면만 붙였다.
- 화면(② 유사과제 확인, `web/src/routes/Precheck.tsx`): 알림에 `tier === "national_rnd"` 가 하나라도 있으면 `ntisOutcomes(request)` 를
  react-query 로 1회(`retry: false`, `staleTime: Infinity`) 호출한다. 결과는 `features/idea/NtisInsights.tsx`:
  - 과제 카드(projects[]): 티어 배지·차단 배지·유사도·제목(비신뢰)·doc_id·캐시 표시 + **주요 성과 (참고용)** — 종류(논문/특허)·제목·연도·학술지/기관·
    등록번호, 5건까지 보이고 초과분은 "성과 n건 더 보기"(`aria-expanded`/`aria-controls`). `error` 가 있으면 "성과를 가져오지 못했습니다 (예외명)", 0건이면 안내.
  - **NTIS 추천**(ntis_recommended[]): 제목 링크(`target=_blank` + `rel="noopener noreferrer"`, sr-only "(외부 링크, 새 창)")·점수·순위·과제번호,
    머리에 "외부 링크 · 미검증" 문구. 블록 끝에 `notice` 를 작은 캡션으로.
  - 503(키 없음)·그 밖의 오류 → "NTIS 성과 조회 불가" 한 줄(`text-muted-foreground`)만. 오류 배너·토스트 없음, 다음 단계 버튼에 영향 없음.
  - 모든 API 텍스트는 `UntrustedText`(텍스트 노드)로만 — fixture 의 `<b>`·`<script>` 가 요소로 해석되지 않음을 Vitest 가 확인.
- 티어 라벨: `web/src/lib/tiers.ts` `tierLabel()` — 서버 `tier_label` 우선, 비면 `national_rnd → 국가R&D 과제` 등으로 보충. 알림 표(`AlertsTable`)와
  차별성 비교표(`ComparisonTable`, 종전엔 raw `tier` 배지)에 적용.
- 타입·클라이언트: `api/types.ts` `NtisOutcome`·`NtisProjectInsight`·`NtisRecommended`·`NtisOutcomesOut`, `api/endpoints.ts` `ntisOutcomes()`
  (기존 `request()` 래퍼 → 세션 쿠키·X-RRA-CSRF 그대로). `schema.d.ts` 는 건드리지 않음(docs/openapi.json 미수정 원칙).
- 가짜 모드(e2e): `adapters/fake/ntis.py` `ScriptedNtisInsights`(outcomes 논문 1·특허 1, related 2건 — 모두 "(가짜)") 를 `composition.build_fake_parts` 가
  `NtisProjectInsights(fake, fake, repo=repo)` 로 조립해 `build_api` 가 가짜일 때 `ntis_insights` 로 넘긴다(실 어댑터·설정 미수정). 시드 문서 `ntis:fake-1`
  (source ntis, doc_type rnd_project) 은 **청크 없이** 넣고 `InMemoryDocumentRepository.find_similar` 가 청크 없는 문서를 제목·초록으로 점수 매기게 해서
  precheck 에는 `national_rnd` 근접 알림으로 잡히되 생성 근거(hybrid_search)에는 들어가지 않는다 — 기존 가짜 흐름 테스트(`internal_doc_ids == ["alio:fake-1"]`)
  와 reranker 가 있는 로컬 환경의 근거 순서를 바꾸지 않기 위해(청크로 넣으면 reranker 가 NTIS 청크를 1위로 올려 깨졌다).
- 검사: backend `pytest -n auto` 1,530 통과·16 skip, lint-imports 8 kept, ruff check/format 통과. web `npm run lint`·`typecheck` 통과, Vitest 56(14 파일, 새
  `NtisInsights.test.tsx` 5건: 렌더·더 보기·외부 링크 속성·비신뢰 텍스트·axe, 503 안내, 티어 라벨, ② 화면 1회 호출·미호출), Playwright 11(새 `e2e/ntis.spec.ts`
  — 가짜 백엔드에서 라벨·성과·추천·링크 속성·콘솔 오류 0), `npm run build` Precheck 청크 6.9 KB gzip.
- 캡처: `docs/history/screens/2026-10-27-web-ntis-01-precheck.png`(가짜 모드, 1280px).
- 주의(통합 세션 참고): `adapters/reranking/cross_encoder.py` 의 `_scores` 는 `to_thread` 만 있고 잠금이 없어, 비교표(`/precheck/comparison`)와
  NTIS(`/precheck/ntis-outcomes`) 가 **동시에** precheck(reranker) 를 돌리면 로컬 MPS 에서 Metal 단언(`A command encoder is already encoding…`)으로
  API 프로세스가 죽었다(전체 e2e 첫 흐름에서 재현, CI 는 모델이 없어 무관). 화면은 비교표가 끝난 뒤(`!cmp.isFetching`) NTIS 를 부르도록 직렬화했다.
  서버 쪽 근본 조치(reranker 어댑터에 `asyncio.Lock`)는 웹 레인 범위 밖이라 하지 않았다 — 배포기에서 여러 화면이 동시에 precheck 를 부르면 같은 위험.
- 남은 일: 실키·IP 반영 뒤 실응답으로 성과 종류(kind)가 paper/patent 외로 오면 `KIND_LABEL` 보충; 과제 상세 링크(`NTIS_PROJECT_URL`) 실확인은 레인 N 대기 항목 그대로;
  docs/status.md·openapi.json·README 는 통합 세션이 갱신.
