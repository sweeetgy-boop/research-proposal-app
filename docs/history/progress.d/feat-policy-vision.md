# 진행 메모 — feat/policy-vision (레인 D, 2026-10-27)

- 00:00 시작. 크롤 레인 산출물(korail-web-crawl.md·korail_web 어댑터) 아직 없음 → manifest 형식을 `docs/vision-manifest.md` 로 정의하고
  읽기 쪽을 별칭 허용으로. ocrmac·pillow 설치, PIL 그림에서 Vision OCR 확인(한글·숫자 인식 OK, `-I` 자식 + rlimit(NOFILE 64·DATA 2GB)
  아래에서도 동작, 장당 ≈1초).
- 00:30 domain(모델·거르기·계획·신뢰도·개인정보) + ports + usecases(read_images·link·sample) 작성. 설계 결정: 이미지 1건 = 문서 1건
  (`text_basis=image_vision`), chunk.basis 는 documents JOIN 이라 스키마 변경 없음. `SourceType` 에 `korail_web` 을 넣으면 assistant
  "미수집 자료원" 테스트 2건이 깨져 되돌림 — 크롤 레인이 넣는다. 적재는 페이지 문서의 source 를 따르고 없으면 `unknown_source` 건너뜀.
- 01:00 adapters: rate_limiter(+openai_compat 배선·Retry-After), vision_reader(data URL parts), manifest·store·ocr_mac·_ocr_worker.
  `_sandbox` 를 부트스트랩 방식(`-I -c`, 부모 패키지 루트 삽입)으로 바꿔 워크트리에서도 자식이 같은 코드를 쓰게 함. config/vision.yaml,
  llm.yaml stage vision·gemini.rate, composition build_*, CLI vision read/sample.
- 01:30 테스트 79건 → 9건 실패 수정(numbers.py 는 "만명" 을 단위로 안 봄 → bare 1,234 로 대조; privacy 부서 보존; 순서 테스트의
  page_url 기본값이 vision 키워드). 전체 1318 통과. 첫 커밋.
- 01:50 `rra vision ingest`(캐시→DB, 호출 없음) + 테스트 4건, 문서(ADR 0016·architecture §4.17·status/timeline 조각·manifest 형식).
