# [23] feat/figures-wide 진행 메모 (2026-10-28 밤, 레인 C)

- 시작. COMMON·ADR 0029/0030/0033·figures.yaml·techniques.yaml·render.py·usecases/figures.py·hwpx.py 읽음.
  실물 양식 쪽 정의: 폭 59528·높이 84189(A4), 좌우 여백 7086, 본문 단락(paraPr 42) 오른쪽 1750 → 그림 폭 43606 HWPUNIT = 153.8mm,
  높이 상한(쪽 1/3) 99.0mm. 폭 153.8mm 에서 viewBox 1600 기준 글자 1단위 = 0.2725pt → 9pt = 33단위(기존 상자 글자 30 = 8.2pt).
- 21:40 origin/main(#88 공용 부품) 병합. 그림 [다시 만들기]·[말로 고치기]·[다른 기법으로 바꾸기]·[다른 그림 추가]·[다시 시도] 를
  useAiCall + AiWaiting(경과 초·[취소]), REST 3경로 cancel_on_disconnect.
- 22:00 백엔드 완료: domain/rules/figure_fit(가로 비율·본문 폭·높이 상한·글자 pt·글자 줄이기·OCR 어림), 밑그림 가로 배치·글자 하한
  (33단위)·넘침 표시, 그림 단계 맞춤 반복(덜 넓은 비율 → 글자 줄이기 → 넓은 비율), 4:1 = 21:9 생성 + 흰 여백 자르기,
  adapters/rendering/hwpx_geometry(양식에서 본문 폭), HWPX 그림 폭·높이 상한·placement.fit, manifest figure_fit, views display_name·fit.
  테스트 +55 백엔드·+2 vitest·e2e 1 확인 추가. OCR 보정 box_em = 1.20(밑그림 16줄, 1.13~1.44).
- 22:10 한/글 Quick Look 확장(HwpQLExtViewAsThumbnails)으로 실물 쪽 미리보기 가능 확인 (Swift QLThumbnailGenerator, 첫 쪽).
- 하는 중: Nano Banana 실측(레인 카운터, 상한 40) → 샘플·쪽 미리보기·eval 문서·ADR 0041·PR.
