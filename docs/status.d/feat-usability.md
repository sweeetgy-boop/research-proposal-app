## feat/usability — 사용자 관점 검토 반영 U1~U8 (2026-10-27, ADR 0017)

규모: 테스트 1,292 통과·18 skip (+53), import-linter 8 kept, ruff 통과. 설정 `config/usability.yaml`(`UsabilityConfig`,
`config_loader.usability_config`) — 항목별 켜고 끔, 기본 전부 켬. 끄면 해당 REST 는 503(`FeatureDisabled`), CLI 는 사용법 오류.

| 항목 | 내용 | 근거 |
|---|---|---|
| U1 근거 원문 바로보기·적합성 | 문장 id 로 근거마다 발췌·제목·자료원·발행기관·연도·수집일(raw.ingested_at)·근거 수준(원문/공개 요약/초록/제목/이미지 판독, summary·title·image_vision 은 `needs_check`)·Argon `support`·제안자 판단. Argon 1차 검토 응답에 `support`(지지·부분·불일치) 추가(추가 호출 없음, `ReviewRound.support`), 불일치 → `evidence_mismatch` 경고. 판단 approve/replace(검색 집합 id 만)/exclude → 새 버전(`DraftVersion.evidence_decisions`), 근거 필수 섹션 전부 제외 → `evidence_all_excluded` 경고 | `domain/rules/evidence.py`, `review.py`(EvidenceDecision·support), `review_draft.py`(support), `prompts/review.md`, `run_manager.sentence_evidence/decide_evidence`; `tests/domain/test_usability_rules.py`, `tests/application/test_usability_manager.py` |
| U2 간편 입력 | 자유 문장(+가제) → 로컬 모델 1회 → 4칸 JSON. 원문에 없는 수치·고유명 칸은 비움, 빈·짧은 칸 보완 질문 0~4개, `merge_answers` 순수 합치기 → 미리보기 → 기존 POST /v1/runs. 저장 없음 | `domain/rules/structure.py`, `models/structure.py`, `usecases/structure_idea.py`, `prompts/structure.md`, `PromptLibraryPort.structure`; `tests/domain/test_structure_comparison_brief.py`, `tests/application/test_structure_brief_compare.py` |
| U3 섹션별 AI 다시 쓰기·보완 질문 | `GenerateProposal.rewrite_section`(같은 지시·스냅샷, [제안자 보완 메모]·[보존 문장] 추가), 제안자 문장 보존·선택값 불변, 후보 `rewrites/rewrite_<key>.json` → 반영 시 버전(origin edit, "AI 다시 쓰기"). 체크리스트 `config/templates/section_checklists.yaml`(요소·질문·키워드) → 빠진 요소 질문, 답은 `proposer_notes.json` | `domain/rules/rewrite.py`·`checklist.py`, `run_manager.rewrite_section/apply_rewrite/section_questions/save_section_answers`, `RunStorePort.save_rewrite/load_rewrite/clear_rewrite/save_notes/load_notes` |
| U4 차별성 비교표 | precheck 상위 5건 × 연구목표·연구방법·적용범위·기대성과·차별화 방향. 기존 과제 칸은 요약·초록 머리말 추출(`section_sentences`), 제목뿐이면 "정보 없음(제목 기준)". 제안 칸은 입력(goal·limitation·beneficiaries·constraints·remarks·differentiation). 양식 밖 | `domain/rules/comparison.py`, `models/comparison.py`, `usecases/compare_projects.py` |
| U5 선행연구 브리핑 | 검색(retrieve) 상위 논문·보고서 10건(문서당 1청크) → LLM 1회(`llm.yaml stages.brief` = gemini, 키 없으면 compose 로컬·fallback_local) → 한 줄 요약(청크 밖 수치 폐기)·연도별 건수·키워드·연구 공백 후보(evidence 필수, "후보" 라벨). 고른 id 는 `RunIn.priority_evidence`/`generate --priority-evidence` → `proposer_notes.json` → retrieve 뒤 `snapshot.priority_ids`(검색 집합 안만) + 청크 앞세움 | `domain/rules/brief.py`, `models/brief.py`, `usecases/brief_prior_work.py`, `prompts/brief.md`, `run_manager._prioritize`, `RetrievalSnapshot.priority_ids` |
| U6 추진일정·성과지표 | `constraints` 에 연구기간(년·개월)이 있으면 연구방법 프롬프트에 [추진일정](개월, 합 ≤ 기간), 기대효과 3섹션에 [성과지표](측정 방법, 목표치 없으면 "목표치 확인 필요"). 일정 합 > 기간 → `schedule_exceeds_period` 경고(`GenerateProposal.lint_draft`, 생성·버전 저장 공용) | `domain/rules/schedule.py`, `generate_proposal.py`(`schedule_metrics`) |
| U7 제출 전 점검 | 필수 섹션·미해결 알림(코드별)·근거 승인 비율·남은 메모·최종 검토 이후 수정·선택형 확정·칸 길이(render_check)·전략 목록 출처(`usability.yaml strategy_source`)·검토 상태. 항목마다 `target` | `usecases/submit_check.py`, `run_manager.submit_check` |
| U8 시범운영 측정 | `runs/<user>/<id>/usage.json`(`UsageRecord`: 단계별 초·총 초·checklist_coverage(검토 결과에 있을 때)·근거 판단 수/비율·다시 쓰기 횟수·HWPX 성공·만족도). finalize 성공/실패 기록, 만족도는 finalized 뒤(1~5, 200자, 이메일·전화 거부). manifest `usage` 는 개수·성공·점수만(허용목록) | `models/usage.py`, `domain/rules/usage.py`, `usecases/usage_report.py`, `RunStorePort.save_usage/load_usage`, `adapters/logging/file_run_log.py` USAGE_KEYS |

### 설정 플래그 (`config/usability.yaml`)
`evidence_view`·`evidence_support`·`evidence_decisions`(U1), `quick_input`(U2), `section_rewrite`·`section_questions`(U3),
`comparison`(U4), `brief`(U5), `schedule_metrics`(U6), `submit_check`(U7), `usage_record`·`feedback`(U8),
`strategy_source: confirmed|draft`. 그 밖: `config/llm.yaml stages.brief`(신규), `config/templates/section_checklists.yaml`(신규).

### CLI
`rra structure --text … [--title] [--json]`, `rra compare <5슬롯> [--differentiation] [--json]`, `rra brief <5슬롯> [--json]`,
`rra runs submit-check <run_id> [--json]`, `rra usage report [--json]`, `rra generate --priority-evidence id1,id2`.

### 프론트엔드 영향 (REST 추가·변경 — docs/openapi.json 은 통합 세션이 `rra api schema` 로 재생성)
- `POST /v1/ideas/structure` 요청 `{text(≤2000), title?}` → `{fields{current_state,root_cause,limitation,goal}, labels, questions[{field,label,question,reason}], skip_allowed, complete, provider, model, parse_failed, notice}`. 꺼짐/LLM 없음 503.
- `POST /v1/ideas/structure/merge` 요청 `{fields, answers}` → 위와 같은 모양(LLM 없음).
- `POST /v1/precheck/comparison` 요청 ProposalRequest → `{notice, blocking, alerts[], comparison{aspects[{key,label}], proposal{title,cells{…}}, projects[{doc_id,title,tier,similarity,blocking,basis,title_only,cells{objective,method,scope,outcome,differentiation}}]}}`.
- `POST /v1/precheck/brief` 요청 ProposalRequest → `{notice, skipped_reason, provider, model, fallback_local, transfer, items[{doc_id,chunk_id,title,source,doc_type,year,basis,summary,summary_missing}], years{연도:건수}, keywords[], gap_label, gaps[{text,evidence[]}], discarded[]}`.
- `POST /v1/runs` 본문에 `priority_evidence?: string[]`(≤50) 추가.
- `GET /v1/runs/{id}/sentences/{sid}/evidence` → `{run_id, sentence_id, notice, evidence[{evidence_id,doc_id,chunk_id,text,title,source,source_label,orgs[],year,ingested_at,basis,basis_label,needs_check,needs_check_label,support,decision,in_snapshot,trust}]}`. 없는 문장 404.
- `POST /v1/runs/{id}/evidence-decisions` 요청 `{decisions[{sentence_id,evidence_id,action: approve|replace|exclude, replacement?}], note?, base_version?}` → `{run_id, status, …version_payload}`(새 버전 또는 같은 내용이면 현재 버전). 규칙 위반·기준 버전 불일치 409.
- `POST /v1/runs/{id}/sections/{key}/rewrite` → `{run_id, notice, section, created_at, dropped, rows[{index,current{text,evidence,origin}|null,candidate{text,evidence,origin,preserved}|null}], candidate[{index,text,evidence,origin,source}], choices[]}`. 편집 불가 상태·없는 섹션·특이사항 409.
- `POST /v1/runs/{id}/sections/{key}/rewrite/apply` 요청 `{chosen?: int[], base_version?, note?}` → `{run_id, status, …version_payload}`. 후보 없음·기준 버전 불일치 409.
- `GET /v1/runs/{id}/sections/{key}/questions` → `{run_id, section, questions[{element,question}], coverage, answers{}}`.
- `POST /v1/runs/{id}/sections/{key}/answers` 요청 `{answers{요소: 답}}` → `{run_id, section, answers{}}`.
- `GET /v1/runs/{id}/submit-check` → `{run_id, ok, failing, items[{key,label,ok,detail,count,target,target_label, …extra}]}` (key: required_sections·unresolved_alerts·evidence_approval·open_memos·stale_edits·choices_confirmed·field_limits·strategy_source·review_state; target 은 `section:<key>`|`sentence:<sid>`|`route:<hint>`).
- `GET /v1/runs/{id}/usage` → `{run_id, usage{step_seconds, total_seconds, checklist_coverage, evidence{approve,replace,exclude,total,ratios}, rewrites, hwpx_success, satisfaction, updated_at}}`.
- `POST /v1/runs/{id}/feedback` 요청 `{score 1~5, comment?≤200}` → `{run_id, usage}`. finalized 전 409, 이메일·전화 포함 422.
- 변경: `version_payload` 에 `evidence_decisions[]`, `review_payload` 에 `support{}` 추가. 기능이 꺼지면 해당 경로 503.

### 하지 않은 것 (이유)
- Streamlit 패널·MCP 도구: 웹 레인(U9)이 화면을 만들고, MCP 는 선택 항목이라 생략. 필요하면 `RunManager` 메서드를 그대로 노출.
- `docs/openapi.json`·`docs/architecture.md`·`docs/status.md` 갱신: 통합 세션 소유.
- U5 섹션별 검색 훅: main 에 `retrieve_sections` 가 없어 `snapshot.priority_ids` + 청크 순서까지만. 생성 레인이 섹션 검색에서 이 id 를 앞세우면 된다.
- U8 `checklist_coverage`: 검토 결과에 그 필드가 있을 때만 기록(main 의 ReviewRound 에는 아직 없음 → None).
