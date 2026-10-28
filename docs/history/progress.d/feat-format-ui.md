# feat/format-ui 진행 메모 (레인 D — HWPX 서식과 화면 편의)

- 17:10 시작. 실물 템플릿·원본 단락 속성 덤프(장·항목·세부 제목이 공백 들여쓰기, 3장 가. 만 내어쓰기,
  특이사항 본문은 제목 복제로 13pt 굵게, 실용화 계획 칸 10pt, 활용계획 목록 칸은 단락 모양 3종, 그림 캡션은
  문서 끝 단락 서식(17pt)을 물려받음) 확인.
- 17:40 `adapters/rendering/hwpx_format.py`(단계별 단락 모양·글자 크기·앞 공백·표 칸·캡션 점검+고침) 연결,
  골든 10건 실물 템플릿 렌더 remaining 0. 실물 닮은 fixture `tests/fixtures/hwpx/proposal_form_like.hwpx`
  (`tests/tools/make_form_like_template.py`) + 테스트 12건.
