# 레인 A — feat/policy-crawl (2026-10-27) 전달 사항

## 전달한 것
- **[C] 공사 홈페이지 스냅샷** `src/rra/adapters/sources/korail_web/` (`_html` 해석·`_pii` 개인정보 제거·`robots`·`snapshot`·`crawler`·`source`·`strategy`), 설정 `config/korail_web.yaml`(메뉴 50), `rra crawl korail --explore|--download [--incremental]`, 탐색·경과 `docs/korail-web-crawl.md`. 수집 대상은 `info.korail.com`(allowed_domains 추가). 스냅샷 `data/korail_web/snapshots/2026-10-27/`(진행 중: 229항목·207파일·654MB, 보도자료 약 1,350건 남음).
- **[P1] 적재 어댑터** `korail_web`(SourceType, DocType `policy`·`korail_news`, visibility public, `raw.crawl_snapshot`·`menu_path`·`terms`·`text_layer`), sha256 중복 제거, 저장 전 `strip_pii`, 삭제 표시 항목 제외. `SOURCE_LABELS`·`rra ingest --source korail_web`.
- **[P2] 스냅샷 운영** 예약 없음. `rra sources status`(신규)와 `GET /v1/sources/status` 의 `korail_web` 행에 `snapshot`·`snapshot_items`·`snapshot_label`("공사 홈페이지 자료: <날짜> 기준 스냅샷"). `rra db backup` 이 `data/korail_web/index.json` + 최신 `manifest.jsonl` 을 사본 옆에 둔다(파일 본체는 백업하지 않음, 다시 받을 수 있음).
- **[P3] 전략체계 초안** `config/templates/korail_strategy.draft.yaml`(5 전략방향·15 전략과제, 항목마다 `basis: text` + 출처 문서·URL·표 위치·스냅샷), `config/strategy.yaml source: draft`, `config_loader.strategy_source/strategy_catalog`, `StrategyCatalog.status`·`label`, REST draft payload `strategy_source`·`strategy_label`, Streamlit 확정 폼 캡션, `rra strategy draft` / `rra strategy promote`(백업 `.bak-<시각>`, source confirmed 로 전환 — 사람만).
- **[P4] 정책 근거 추천** `application/usecases/policy_suggest.py`(korail_web·molit 의 policy 문서만, LLM 없음), `domain/rules/policy_phrases.py`(문장 선택·`policy_basis_text`·`apply_policy_suggestion`), `domain/models/policy.py`, `POST /v1/ideas/policy-suggestions`, `rra policy-suggest [--pick N]`. 제안자가 고른 것만 policy_basis 에 — 자동 삽입 없음, 정책적 중요도 근거 규칙 불변(테스트).
- **[P5] 검색 범위** `domain/rules/retrieval_scope.py` — `policy`·`korail_news` 는 `find_similar`(precheck·generate 유사과제 판정)에서 제외, `NON_OVERLAP_SOURCES`(korail_web·molit)는 "미수집 자료원" 문장에서 제외.
- **[P2-1] 국토교통부 정책자료** `src/rra/adapters/sources/molit/`, `config/molit.yaml`, `rra ingest --source molit`, 판 추적 `domain/rules/editions.py`. **[P2-10]** 포함. P2-2·4·6 은 탐색만(docs/korail-web-crawl.md §4).
- 테스트: `pytest -q` 1,300 통과·18 skip(+76), `lint-imports` 8 kept, `ruff` 통과. ADR 0016.

## 프론트엔드 영향 (docs/openapi.json 은 통합 세션이 `rra api schema` 로 갱신)
- `POST /v1/ideas/policy-suggestions` (본문 ProposalRequest) → `{notice, count, suggestions:[{doc_id,title,year,page,quote,url,menu_path,keywords,similarity,policy_basis_text}]}`; 503 = 기능 꺼짐.
- `GET /v1/sources/status` 행에 `korail_web`·`molit` 추가, `korail_web` 행에 `snapshot`·`snapshot_items`·`snapshot_label`.
- `GET /v1/runs/{id}/draft` 에 `strategy_source`(draft|confirmed)·`strategy_label`(초안이면 "전략체계 초안(확인 전)").

## 통합 세션이 돌릴 것 (무거운 작업)
```bash
# 1) 스냅샷 마저 받기 (보도자료·주요사업·브로슈어; 중단돼도 같은 명령으로 이어 감)
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli crawl korail --download --incremental
# 2) 적재 (첨부 샌드박스 파싱 + 임베딩 — mlx·DB 작업)
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source korail_web --limit 5000
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source molit --limit 300
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli sources status
# 3) 골든셋 01·02 로 정책 근거 추천 확인 (적재 뒤)
for g in tests/golden/01*.yaml tests/golden/02*.yaml; do PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli policy-suggest --file "$g"; done
# 4) 50MB 넘는 보고서(보류 13건)를 받으려면 config/korail_web.yaml max_file_mb: 120 뒤 1) 다시
```

## retrieval_mix.yaml 에 옮길 섹션별 규칙 (의도)
- `policy`(korail_web·molit): 정책적 중요도(제안자 입력 근거 보조·정책 근거 추천), 경영전략 정합성, 필요성. 기술적 중요도·유사과제 판정 금지.
- `korail_news`: 특이사항·현황 보조만. 기술적 중요도·유사과제 판정 금지.
- (예정) `audit` → 정책적 중요도·필요성, `statistics`·`table_facts` → 현황·필요성·기대효과 수치, `procurement` → 유사과제 판정·특이사항, `rnd_notice` → 정책 근거 추천·공고문. 기술적 중요도 = 논문·보고서·특허 우선.

## 남은 것 / 보류
- 스냅샷 완료 대기(위 1). 50MB 초과 보고서 13건 보류. `text_layer: false` PDF 4건(OCR 은 다른 레인).
- P2-2 안전 통계(railsafety 시간 초과, KOSIS/통계누리 API 키 필요), P2-4 감사원(JS 렌더·robots 가 /api/ 금지 → 보류), P2-6 발주 용역(ebid POST 폼 → 나라장터 API 대안, overlap.yaml 새 키·상태 문구 미구현), P2-3·5·7·8·9 미착수.
- Streamlit 에 정책 근거 추천 선택 UI 없음(CLI·REST 만). MCP 도구 없음.
- 전략체계 이미지(전략경영체계도)에서의 항목은 다른 레인(`basis: image_vision`)이 보탠다.
