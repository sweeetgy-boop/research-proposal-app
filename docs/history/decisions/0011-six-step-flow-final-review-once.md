# ADR 0011 — 전체 흐름 6단계, Argon 최종 검토 1회 (2026-10-27)

> 상태(2026-10-29 문서 최신화): 6단계 흐름·최종 검토 1회는 유효. ③ 의 Argon 1차 검토(v1→v2)는 2026-10-28 ADR 0032 부터 끔(작성자가 Argon 이라 자기 검토) — 대신 L2 로컬 2차 검토(ADR 0040).

**배경** 이전 흐름은 "재검토 무제한" 이었다(작성 → 검토 → 수정 → 재검토 …). 호출 비용·제안자 책임이 불분명했다. (대화 기록 기준)
**선택지** (a) 재검토 무제한 유지, (b) 검토 1회 고정, (c) 1차 검토 자동(초안 생성의 일부) + 최종 검토는 요청 시 1회, 이후 수정은 표시만.
**결정** (c). ① 아이디어 입력 → ② 유사과제 확인·과제 추천 → ③ 초안 생성(로컬 작성 v1 → Argon 1차 검토 → 검증 통과분 자동 반영 v2) → ④ 직접 수정·보완(버전 관리, 외부 LLM 없음) → ⑤ Argon 최종 검토 1회(stale 표시, 다시 받기는 선택) → ⑥ 최종 마무리.
**이유** 초안은 "로컬 작성 + Argon 보완" 으로 한 번에 좋게, 제안자 편집은 기록 가능하게, 최종 검토는 제출 직전 1회로 호출을 예측 가능하게.
**결과** [E] 브랜치 feat/draft-pipeline, PR #22 (2026-10-27). `review_flow` 재정의(표 테스트 19행), `PipelineConfig`/`config/pipeline.yaml`,
1차 검토 자동 반영 → v2(origin=argon, 폐기·의견은 annotations), `domain/rules/versions`(문장·섹션 편집·diff·stale 수), 임시 저장·
VersionConflict, 최종 검토(kind=final, score_delta)·stale·다시 받기 횟수, finalize(version 선택·stale 경고). 키가 없으면 v1 로
진행·review_skipped → ⑥. 옛 run 의 done·reviewed 는 읽을 때 변환. 가짜 모드 REST 흐름(생성 → 1차 자동 반영 v2 → 저장 → 최종
검토 → 마무리)이 테스트로 고정됐다.
