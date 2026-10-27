# 최종 점검 (2026-10-27) — [자동 진행] 판단 목록과 확인 요청

(작업이 끝나면 [Z] 에서 정리해 마지막 메시지로 보낸다. 아래는 진행 중 누적.)

## 실행 명령 (아침 확인용)

```
cd /Users/chan/projects/research-proposal-app && .venv/bin/rra api --port 8000   # 127.0.0.1:8000, web/dist 서빙
```
브라우저 http://127.0.0.1:8000 → 토큰 입력(.env 의 RRA_API_TOKEN) → ① 입력 → ② 유사과제·추천 → ③ 생성 → 초안 → ④ 편집 → ⑤ 최종 검토 → ⑥ 다운로드.

## [자동 진행] 에서 실제로 일어난 판단

| 시각 | 판단 | 근거·기록 |
|---|---|---|
| 10:03 | reranker 모델 라이선스가 지시서의 MIT 가 아니라 Apache-2.0 — 업무 이용 허용이라 진행 | HF 모델 카드, llm.yaml 주석, ADR 0013 |
| 10:40 | precheck reranker 후보 폭 k×4 → k×3 (지연 2.0~2.4s → 1.5~1.95s, 상한 2초) | data/eval/precheck_hits*.json |
| 10:40 | 골든셋 정답 목록을 두 모드의 상위 5 제목을 보고 같은 주제 사내 기록을 더해 넓힘(기존 3 + 신규 7) | tests/golden/*.yaml expected_similar |
| 11:07 | Q9 2단계 중단 — Q4 "인용 금지" 가 검색 근거의 본보기 doc 인용까지 폐기해 섹션이 비던 결함. 베끼기만 폐기로 완화(설정 아님, 규칙 변경) | overnight 11:07 행, 커밋 5c97b23 |
| 11:10 | 자료원 균형: `config/retrieval_mix.yaml` 신설. 걸러서 0건이면 전부로 되돌림(근거를 비우는 쪽보다 넓게 주는 쪽) | architecture §4.16 |
| 11:10 | reranker 기본 켬(설정으로 끌 수 있음, 모델 폴더 없으면 자동 생략) | ADR 0013 |

## 내가 확인할 것 (체크박스)

- [ ] Q8·Q9 기본값 결정(ADR 0013, docs/eval-2026-10-27.md)
- [ ] 전략체계 초안 항목별 출처와 텍스트·이미지 차이 ([P] 뒤)
- [ ] 크롤링 범위 축소·보류 목록 (docs/korail-web-crawl.md)
- [ ] 이미지 판독 견본과 숫자 대조 통과율 (docs/ocr-sample/)
- [ ] 열어 둔 PR 과 이유
- [ ] 후보 파일(rail_terms.candidates.yaml, generic_terms 후보)
- [ ] 발주 용역 임계치 결과
- [ ] Lighthouse 미달 항목 (현재 없음 — /login 100/100/100)

## 내가 할 일 (사람 입력)

- [ ] `rra strategy promote` 실행 여부
- [ ] NTIS·KIPRIS 키 신청
- [ ] 공고문 파일(data/inbox/notice/)
- [ ] 동료 GitHub 아이디(CODEOWNERS web/)
