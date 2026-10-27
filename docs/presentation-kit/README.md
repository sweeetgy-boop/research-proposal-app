# 발표 자료 구성안 (docs/presentation-kit)

연구과제 제안서 작성 보조 Agent(RRA)를 소개하는 발표를 위한 원천 묶음. 수치·그림은 전부 `docs/history/` 에서 가져온다
(연표 `timeline.md`, 수치 `metrics.csv`·`charts/`, 결정 `decisions/`, 교훈 `lessons.md`, 화면 `screens/`, 녹화 `demo/`).
이 폴더의 문서는 발표자가 읽는 글이고, 슬라이드는 여기서 뽑아 만든다.

| 파일 | 용도 |
|---|---|
| `summary.md` | 한 장 요약 — 문제·해결·결과·남은 과제 (발표 첫 장·마지막 장) |
| `demo-script.md` | 시연 대본 — 웹 화면 ①~⑥ 순서, 보여 줄 것·말할 것·실패 대비 |
| `qna.md` | 예상 질문과 답 — 보안·비용·정확도·운영·한계 |
| `limitations.md` | 솔직한 한계와 다음 단계 |

## 슬라이드 구성안 (15장, 20분)

| # | 제목 | 내용 | 원천 |
|---|---|---|---|
| 1 | 문제 | 제안서 한 건에 드는 일(유사과제 확인·근거 수집·12개 섹션·양식), 중복 과제 탈락 | `summary.md` |
| 2 | 목표와 범위 | 기획서 Ⅰ 범위 12개·Ⅱ 핵심 기능 7개 중 완료 현황 | `docs/status.md §1` |
| 3 | 전체 흐름 ①~⑥ | 아이디어 입력 → 유사과제 확인·과제 추천 → 초안 생성(로컬 작성+Argon 1차 검토) → 직접 수정 → 최종 검토 → HWPX | `history/diagrams/03-six-step-flow.svg`, ADR 0011 |
| 4 | 구조 | 헥사고날 4계층·import 계약 8건·포트/어댑터, 조립 지점 하나 | `history/diagrams/01-hexagonal-layers.svg`, ADR 0001 |
| 5 | 자료 | 사내 과제 1,119·공시 요약 120·OpenAlex 2,482, SQLite FTS5+벡터(RRF), 관련도 하한·출처 다양성 | `metrics.csv`, ADR 0005·0010 |
| 6 | 유사과제 판정 | 유사도 AND 공유 키워드, 기관별 임계치, 차단/근접, 차별화 제안·과제 추천 | ADR 0004·0012, `screens/` |
| 7 | 초안 생성 | 문장마다 근거 id, 검색 밖 id 폐기, 선택형 제안·확정, 지어낸 수치·외국 문자 경고 | architecture §4.1·§4.7 |
| 8 | 로컬 모델 + Argon | Qwen 7B 작성(비용 0, 사내 자료 외부 유출 최소) + Gemini Argon 검토(점수·수정안·추가 문장), 전송 범위 manifest | ADR 0003·0006·0007, `llm-bench-2026-10-26.md` |
| 9 | 초안 품질 강화 8가지 | 보강 질문·설계도·섹션별 검색·본보기·보완 작성·규칙 검사·두 후보·reranker, 측정으로 기본값 결정 | ADR 0013, `docs/eval-2026-10-27.md` |
| 10 | 편집·버전·최종 검토 | 문장 단위 수정·메모·비교·복원, 최종 검토 1회·stale 경고, 양식 파일은 finalize 로만 | ADR 0011, `screens/` |
| 11 | 보안 | A~J 규칙(비신뢰 텍스트·샌드박스·허용 도메인·SecretStr·바인딩·XML escape·127.0.0.1·동시성 1·로그 허용목록) | architecture §7 |
| 12 | 검증 | 테스트 수·계약·CI·골든셋·Lighthouse/axe(웹) | `metrics.csv`, `charts/` |
| 13 | 시연 | 웹 화면 ①~⑥ (녹화 `history/demo/`) | `demo-script.md` |
| 14 | 한계와 다음 단계 | 키 대기 자료원·전략체계 목록·공고문·공개 방식·골든셋 피드백 루프 | `limitations.md` |
| 15 | 요약 | 한 장 요약 다시 | `summary.md` |

## 수치 갱신 규칙

발표 전에 `tools/history_charts.py` 로 그래프를 다시 만들고, `summary.md` 의 수치를 `metrics.csv` 마지막 행과 맞춘다.
수치마다 근거(커밋·PR·문서)를 괄호에 적는다. "대화 기록 기준, 미검증" 표시가 있는 항목은 발표에서 빼거나 그대로 표시한다.
