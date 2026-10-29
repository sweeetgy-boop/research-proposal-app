# 개발 경과 기록 (docs/history)

발표 자료의 원천. 여기 있는 것만으로 "문제 → 해결 → 결과 → 남은 과제" 를 설명할 수 있어야 한다.

| 파일 | 내용 |
|---|---|
| `timeline.md` | 날짜순 연표(설계 → 핵심 기능 → 화면 → 리팩터링 → 양식 연동 → 작성·검토 구조 → 사내 자료 → 모델 비교 → 협업·자동화 → 근거 확충 → 과제 추천 → 2중 작성·편집·최종 검토 → 초안 품질 강화 → 웹) |
| `metrics.csv` / `metrics.md` | 날짜별 테스트 수, 계약 수, 계층별 코드량, 자료원별 적재 건수, 생성 시간, JSON 성공률, Argon 점수 |
| `charts/` | `tools/history_charts.py` 가 metrics.csv 로 만든 그래프(SVG·PNG) |
| `diagrams/` | 구조도 Mermaid 원본(`.mmd`)과 SVG |
| `decisions/` | 결정 기록(ADR) |
| `lessons.md` | 겪은 문제와 해결 |
| `screens/` | 화면 캡처(날짜 붙임). Streamlit(웹 이전 기준)과 웹 전후 비교, 2026-10-29 Research Studio 전후(`2026-10-29-ui-studio-*`) |
| `deploys/` | 시범 배포 기록(`tools/deploy.sh`)과 반영 대기 목록 `pending.md` |
| `demo/` | e2e 녹화(웹 단계에서 추가) |

유지 규칙(CONTRIBUTING·PR 템플릿): 모든 PR 은 합치기 전에 `timeline.md` 에 항목 하나(날짜·무엇·왜·PR 번호·핵심 수치),
수치가 바뀌었으면 `metrics.csv` 에 행, 주요 결정은 `decisions/` 에 ADR, 화면이 바뀌었으면 `screens/` 에 캡처.

## 발표용 한 장 요약

> 2026-10-29: 최신 요약은 `docs/presentation-kit/summary.md`, 보고서 재료는 `docs/final-report-materials.md`. 아래는 2026-10-26 기준 요약(이전 방식: 로컬 7B 작성 + Argon 1차 검토)이다.

**문제.** 철도연구원의 연구과제 제안서(별지 제2호서식)는 유사·중복 과제 확인, 근거 수집, 12개 섹션 작성, 양식 채우기를 제안자가
손으로 한다. 과거 과제 1,119건·공시 요약 120건·논문을 매번 다시 찾기 어렵고, 중복 과제는 심사에서 걸린다.

**해결.** 근거 기반 작성 지원 Agent(RRA). 사내 과제·공시 요약·OpenAlex 논문(2,482건)을 SQLite(FTS5 + 벡터, RRF)에 적재하고
① 아이디어 입력 → ② 유사과제 확인(유사도 AND 공유 키워드)·차별화 과제 추천 → ③ 초안 생성(로컬 Qwen 7B 작성 + Gemini Argon 1차
검토로 보완, 문장마다 근거 id) → ④ 제안자 직접 수정(버전 관리) → ⑤ Argon 최종 검토 1회 → ⑥ HWPX 양식 출력.
헥사고날 구조·보안 규칙 10개(비신뢰 텍스트, 샌드박스 파싱, 허용 도메인, SecretStr, 파라미터 바인딩, XML escape, 127.0.0.1 바인딩…).
모든 외부 전송은 manifest 에 doc_id 단위로 남는다.

**결과 수치(2026-10-26 기준).** 테스트 1,178건(LLM·임베딩 없이), import 계약 8건, CI 통과. 자료원 own 1,119 / alio 120 / openalex 2,482.
JSON 형식 성공률 96.5%(Qwen, 교정 재요청 포함), 12개 섹션 생성 105~145초, Argon 검토 36초·4개 기준 점수(3/2/3/3).
무관한 입력 인용 0건(관련도 하한), 근거 구성 alio 9/own 6/openalex 6(출처 다양성).

**남은 과제.** 차별화 과제 추천·2중 작성·편집·최종 검토(2026-10-27 야간), 초안 품질 강화 8가지의 효과 측정, 웹 프론트엔드,
API 키(KIPRIS·NTIS·ScienceON)·전략체계 목록·공고문 투입, Mac mini 운영 등록과 공개 방식 결정.
