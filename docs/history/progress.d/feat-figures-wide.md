# [23] feat/figures-wide 진행 메모 (2026-10-28 밤, 레인 C)

- 시작. COMMON·ADR 0029/0030/0033·figures.yaml·techniques.yaml·render.py·usecases/figures.py·hwpx.py 읽음.
  실물 양식 쪽 정의: 폭 59528·높이 84189(A4), 좌우 여백 7086, 본문 단락(paraPr 42) 오른쪽 1750 → 그림 폭 43606 HWPUNIT = 153.8mm,
  높이 상한(쪽 1/3) 99.0mm. 폭 153.8mm 에서 viewBox 1600 기준 글자 1단위 = 0.2725pt → 9pt = 33단위(기존 상자 글자 30 = 8.2pt).
- 하는 중: 비율 규칙·맞춤 규칙(domain) → 밑그림 가로 배치·글자 하한 → 그림 단계 맞춤 반복 → HWPX 폭·manifest.
