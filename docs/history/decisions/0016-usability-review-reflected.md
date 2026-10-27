# ADR 0016 — 사용자 관점 검토 반영 (2026-10-27, feat/usability)

**배경** 외부 사용성 검토(10.15 기획서 대상)에서 받은 의견: ① 문장 옆 근거 id 만으로는 근거가 맞는지 알 수 없다,
② 필수 4칸 입력이 부담스럽다, ③ 섹션 하나만 다시 쓰고 싶다, ④ 유사과제와 무엇이 다른지 표로 보고 싶다,
⑤ 선행연구를 먼저 훑고 싶다, ⑥ 연구기간이 있는데 일정·성과지표가 없다, ⑦ 제출 전에 빠진 것을 한 번에 보고 싶다,
⑧ 시범운영 효과를 숫자로 남겨야 한다.
**선택지** (a) 화면만 고친다(백엔드 그대로), (b) 항목마다 도메인 규칙 → 유스케이스 → 얇은 진입점으로 넣고 전부 설정으로
켜고 끈다, (c) 외부 LLM 호출을 늘려 판단을 모델에 맡긴다.
**결정** (b). `config/usability.yaml`(`UsabilityConfig`, 기본 전부 켬)로 U1~U8 을 각각 끌 수 있다. LLM 호출은 늘리지
않는다 — U1 적합성은 Argon 1차 검토 응답에 `support` 를 함께 받고, U2·U3 는 로컬(compose) 모델 1회, U5 는 `stages.brief`
(Gemini, 키 없으면 로컬) 1회, U4·U6·U7·U8 은 LLM 없음.
- U1: 근거 제외(exclude)는 문장의 근거 id 를 지우지 않고 판단만 버전에 남긴다 — 근거 필수 섹션에서 `no_evidence`
  오류(invalid)가 아니라 `evidence_all_excluded` 경고로 머문다. replace 는 이번 run 검색 집합 안의 id 로만.
  support=불일치 → `evidence_mismatch` 경고. 판단·적합성 모두 버전(`evidence_decisions`)·검토 파일(`support`)에 저장.
- U2: 자유 문장은 저장하지 않는다. 원문에 없는 수치·고유명이 든 칸은 비워 보완 질문으로 돌린다(모델이 지어낸 값 차단).
- U3: 제안자가 고친 문장(proposer_edit·proposer_input·app)은 다시 쓰지 않고 원래 자리에 둔다. 후보는
  `rewrites/rewrite_<key>.json` 에 두고 반영 때만 버전(origin edit, note "AI 다시 쓰기")을 만든다. 보완 질문은 설정
  파일 `section_checklists.yaml` 의 요소·키워드로만(규칙), 답은 `proposer_notes.json` 에 제안자 입력으로.
- U4: 기존 과제 칸은 요약·초록의 머리말 추출만, 제목뿐이면 "정보 없음(제목 기준)". 양식에는 넣지 않는다.
- U5: 고른 논문은 `snapshot.priority_ids` + 청크 순서 앞세우기까지만(섹션별 검색 훅은 생성 레인).
- U6: 연구기간은 `constraints` 에서 규칙으로 읽고(년·개월), 일정 합이 기간을 넘으면 경고만. 목표치는 "목표치 확인 필요".
- U7: 항목마다 target(section:/sentence:/route:)을 붙여 화면이 바로 이동한다. 렌더를 막지 않는다.
- U8: `usage.json` 은 시간·비율·횟수·성공 여부·점수만. manifest 에는 개수·성공·점수만(한 줄 소감 제외).
**이유** 판단 규칙이 코드(domain)에 있어 테스트로 고정되고, 끄면 이전 동작과 같다. 외부 전송 범위·보안 A·I 가 그대로다.
**결과** REST 13경로·CLI 5명령 추가, 테스트 1,239 → 1,292. Streamlit 패널·MCP 도구는 넣지 않았다(웹 레인·후속).
