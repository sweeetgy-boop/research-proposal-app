## feat/draft-quality — 초안 품질 강화 [Q] (2026-10-27, ADR 0013, architecture §4.15·§4.16)

| 항목 | 기본값 | 근거 |
|---|---|---|
| Q1 clarify 입력 보강 질문 | 끔(요청 시) | `usecases/clarify_input`, `request.supplement`, CLI `rra clarify`, REST `/v1/precheck/clarify`, MCP `rra_clarify`, Streamlit 패널 |
| Q2 outline 섹션 설계도 | 끔 | `usecases/outline`, step `outline`, outline.json, `rra runs outline`, `GET /v1/runs/{id}/outline` |
| Q3 section_search | 켬 | `retrieve_sections`, `domain/rules/section_search`, `snapshot.section_chunks/section_added` |
| Q4 exemplars | 끔 | `domain/rules/exemplars`(공시 요약 "■ ◦" 파서), 베끼기만 폐기 |
| Q5 additions | 켬 | 체크리스트(U3 와 같은 파일)·`ReviewComment.kind=addition`·`origin=argon_addition`·충족률 |
| Q6 rule_check | 켬 | `domain/rules/style`(어미 통일·중복 제거·경고), 칸 상한 자르기 `section_trimmed`, `lint_draft` 공용 |
| Q7 two_candidates | 끔 | `CORE_SECTIONS`, candidates.json, `candidate_choices`(`rejected_text`) |
| Q8 reranker | 켬 | `ports/reranker`, `adapters/reranking`(bge-reranker-v2-m3, Apache-2.0), precheck k×3 |

측정: `rra eval --label … --pipeline none|all|default --on/--off --no-review --only`, `--report` → `docs/eval-2026-10-27.md`.
그 밖: `config/retrieval_mix.yaml`(섹션별 허용 doc_type·논문 최소 보장·유사과제 제외), 골든셋 10건(`tests/golden`, `expected_similar`),
`POST /v1/runs acknowledged`(409 게이트), 초안 문장 `sentence_id`, 근거 패널 `url`, ScienceON 적재가 질의·target 서버 오류를 건너뜀.
사람 입력: 전략체계 목록 확정(`rra strategy promote`), ScienceON .env 키 맞바꾸기.
