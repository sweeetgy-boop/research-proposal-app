# 레인 E — feat/policy-sources (2026-10-27) 전달 사항

[P2] 보류 항목 처리: P2-2 안전 통계, P2-3 운영·수송 통계, P2-4 감사원(국정감사 보류), P2-5 경영평가, P2-6 발주 연구용역, P2-10 판 추적 확인.
탐색·결정 기록은 `docs/korail-web-crawl.md` §5, 경과 `docs/history/progress.d/feat-policy-sources.md`, ADR 0021.

## 전달한 것
- **도메인**: DocType `statistics`·`audit`·`procurement`, SourceType `g2b`·`bai`·`mofe`·`datago`, Tier `procurement`("발주 용역", 임계치
  0.80 = own 과 동일, `DEFAULT_THRESHOLDS`), `STATUS_LABELS`(procuring → "용역으로 진행 중/예정", procured → 기간 경과), `SOURCE_LABELS` 4건,
  `NON_OVERLAP_SOURCES` += bai·mofe·datago(g2b 는 판정 자료원), `retrieval_scope.OVERLAP_EXCLUDED_DOC_TYPES` += audit·statistics.
  `no_overlap_statement` 기준 문장에 "발주 용역 0.80" 추가. **P2-10**: `editions.mark_editions` 모호(최신 판 등록일 미상) → 둘 다 현행 + `ambiguous`.
- **어댑터 4개**: `adapters/sources/procurement/`(g2b, 나라장터 입찰공고 용역 API, `RRA_DATA_GO_KR_KEY` 없으면 MissingCredential),
  `adapters/sources/audit/`(`bai_crawler.py` Playwright 공개 화면 조작 → 스냅샷, `bai_source.py` 스냅샷 → Document, `mofe.py` 기재부 경영평가 보도자료),
  `adapters/sources/datago/`(공공데이터포털 파일데이터, 키 없음, CSV→표 텍스트 앞 400행). 설정 `config/g2b.yaml`·`bai.yaml`·`mofe.yaml`·`datago.yaml`,
  `security.yaml allowed_domains` += www.bai.go.kr·mofe.go.kr, `korail_web.yaml biz_stat_docs` doc_type statistics.
- **진입점**: `rra crawl bai [--incremental] [--json]`, `rra ingest --source g2b|bai|mofe|datago`, `rra sources check --source g2b`, `rra sources status` 행 4개(자동),
  REST/Streamlit 알림에 `status_label`(web `AlertsTable` 는 `status_label ?? status`).
- **수집물**(미커밋): `data/bai/snapshots/2026-10-27/` — "철도" 55항목, 파일 40개(전문 pdf 20·hwp 공개문 20) 82.5MB, 보류 1(srno 1849 → `--incremental` 로 재시도).
  g2b 는 키가 없어 수집물 없음. datago·mofe 는 적재 시 내려받는다(`data/datago/`·`data/mofe/`).
- 시운전(스크래치 DB `RRA_DB_PATH`, `--limit 3`): datago 3·mofe 3 → 6문서 34청크(실서버·샌드박스·임베딩 포함), bai 3 → 3문서 160청크.
- 테스트: `pytest -q` 1,519 통과·17 skip(+28), `lint-imports` 8 kept, `ruff` 통과. 새 테스트 tests/adapters/{procurement,audit,datago}, tests/domain/test_editions_and_procurement_tier.py.

## 내가 할 일 (API 키 — .env 에 넣고 chmod 600)
| 키 | API 이름 | 제공처 | 신청 URL | 쓰임 |
|---|---|---|---|---|
| `RRA_DATA_GO_KR_KEY` | 조달청_나라장터 입찰공고정보서비스 (`BidPublicInfoService`, 용역 조회 `getBidPblancListInfoServcPPSSrch`) | 공공데이터포털(조달청) | https://www.data.go.kr/data/15129394/openapi.do (검색: "나라장터 입찰공고정보서비스") — 로그인 → 활용신청(자동승인) → 마이페이지 일반 인증키 | P2-6 `g2b`. 키 투입 뒤 `rra sources check --source g2b` → `python -m tests.tools.record_fixture` 류로 실응답 녹화 → `FIELDS` 확정 |
| (선택) `RRA_DATA_GO_KR_KEY` 동일 키 | 한국철도공사_수송실적 OpenAPI(있을 때) · KOSIS 통계 OpenAPI(`kosis.kr/openapi`, 별도 키) | 공공데이터포털 / 통계청 KOSIS | https://www.data.go.kr (검색 "한국철도공사 수송") / https://kosis.kr/openapi/ | 2순위 — 파일데이터(datago)가 키 없이 같은 통계를 주므로 지금은 미구현 |
키 없이 되는 것: datago(파일데이터), bai(Playwright), mofe. Playwright 는 pyproject 에 넣지 않았다 — 수집 기기에서 `uv pip install playwright && playwright install chromium`.

## 통합 세션이 돌릴 것 (무거운 작업)
```bash
# 1) 감사원 스냅샷 보충(2차가 끝나지 않았으면) — 같은 날 스냅샷에 이어 받음
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli crawl bai --incremental
# 2) 적재 (샌드박스 파싱 + 임베딩)
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source bai --limit 100
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source mofe --limit 20
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source datago --limit 30
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source korail_web --limit 5000   # biz_stat_docs 가 statistics 로 다시 적재되게
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source g2b --limit 200 --skip-unavailable   # 키 있을 때만
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli sources status
# 3) 골든셋 01 로 섹션별 근거 구성 확인 (architecture §4.16 규칙)
```

## retrieval_mix.yaml 에 반영할 규칙 (의도 — 통합 담당이 config 에 모음)
- `procurement`(g2b): 유사과제 판정에 "발주 용역" 티어로 포함(`overlap_exclude` 에 넣지 않음), 섹션은 `overlap_review`·`utilization` 만(이미 있음).
- `audit`(bai·mofe): `policy_importance`(정책 근거 추천 후보)·`expected_management`·필요성(objective) 보조. 기술적 중요도·유사과제 판정 금지(이미 overlap_exclude).
  정책 근거 추천(`policy_suggest`)에 audit 을 넣으려면 `POLICY_DOC_TYPES` 확장이 필요 — 이번 레인에서는 바꾸지 않음(판단 요청).
- `statistics`(datago·korail_web biz_stat_docs): 현황·필요성·기대효과 수치(`objective`·`expected_management`, 이미 allow 에 있음). 수치 lint(`unsupported_number`)의
  근거로 쓰이려면 청크에 표 행이 들어가야 한다 — 표 텍스트는 ' | ' 구분 400행 상한.

## 보류 / 남은 것 (이유)
- ebid.korail.com: 목록 POST·JS 적재, 상세 로그인, 약관 미확인 → 쓰지 않음(나라장터 API 로 대체). 과업 개요는 API 에 없음(공고서 첨부 호스트 미정).
- 국정감사 지적사항: 감사원 사이트 밖(국회) → 보류. 경영평가 공사별 개선 권고 본문(평가보고서, 알리오) → 보류, 총괄 보도자료만.
- railsafety.or.kr 접속 시간 초과(2회째) → 파일데이터로 대체. KOSIS·통계누리 API 는 키 필요 → 미구현.
- 감사원 상세 "부서명"(`bai_department`) 미추출(마크업이 dt/th 가 아님) — 적재 영향 없음.
- g2b `FIELDS` 는 명세 기준 후보 — 실응답 뒤 확정(fixture 는 구성 예시로 표시).
- `retrieval_mix.yaml`·`docs/openapi.json`·`docs/status.md`·timeline/metrics 본표는 통합 세션이 갱신(조각만 둠).
