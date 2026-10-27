# ADR 0028 — 유사과제 판정 후보는 과제형 자료원만, 논문·보고서·특허는 "관련 연구"(참고) (2026-10-28, 레인 F2)

## 배경
2026-10-27 저녁 ScienceON 2,045건(논문·보고서·특허)과 NTIS 연구보고서 1,084건·과제 2,000건을 적재한 뒤 골든셋 precheck 적중이
9/10 → 6/10 으로 떨어졌다(`docs/eval-2026-10-27.md` §8.1). 골든셋 01 은 유사과제 상위 8 이 전부 ScienceON 논문(e5 유사도 0.886~0.903)이고
정답(사내 기록 alio/own, 0.84~0.88)이 밀렸다. 논문·보고서·특허는 "기수행 과제" 가 아니므로 중복 판정 대상이 아니고, 차단·근접 알림에
올라오면 제안자가 무엇을 피해야 하는지 알 수 없다. 한편 NTIS 과제 2,000건은 요약이 비슷해 0.87~0.89 로 몰려 사내 기록을 상위 80 밖으로
밀어냈다(01·10).

## 선택지
1. 임계치만 올린다 — 논문이 여전히 사내 기록 위에 서고, 정답 순위는 그대로. 제외.
2. `retrieval_mix.yaml overlap_exclude` 에 paper·report·patent 를 더한다 — ScienceON 보고서는 `internal_report`(알리오와 같은 doc_type)라
   doc_type 만으로는 못 가르고, NTIS 연구보고서(report)도 같은 자료원 안에 과제(rnd_project)와 섞여 있다. 또 `retrieval_mix.yaml` 은
   공유 파일(통합 담당만 수정).
3. **자료원(+doc_type) 목록으로 판정 후보를 정하고, 저장소 검색을 그 자료원 안에서만 한다**(`find_similar(sources=…)`, sqlite-vec KNN
   사전 필터). 논문·보고서·특허는 따로 검색해 `related_research` 로 돌려준다. 후보 풀은 자료원마다 상위 n 건을 먼저 넣고(NTIS 가 사내
   기록을 밀어내지 않게) 나머지를 전체 순위로 채운 뒤 reranker 가 고른 순서를 그대로 알림 순서로 쓴다.

## 결정
- 3. 규칙 `domain/rules/overlap_candidates.py`(`OverlapCandidateRule`, 순수). 목록은 코드가 아니라 `config/overlap.yaml candidates` —
  `project`(own, alio, ntis `rnd_project`, g2b), `research`(scienceon, openalex, kipris_kr, kipris_intl, ntis `report`; k 5),
  `pool`(per_source 6, size 24). 절이 없으면 제한 없음(옛 동작). 로더 `config_loader.overlap_candidates`, 조립 `build_precheck`.
- `RetrievalMix.candidates` 에 같은 규칙을 주입해 `mix.overlap_candidates()` 를 쓰는 생성 단계(retrieve 의 유사과제 판정)도 같은
  후보 집합을 따른다 — F1 레인의 `generate_proposal.py` 는 건드리지 않았다.
- 포트 `DocumentRepository.find_similar(text, *, k, sources=None)`. SQLite 는 `chunk_rowid IN (자료원 청크 부분집합)` 사전 필터
  (`_vec.search_within`, sqlite-vec 0.1.9 에서 0.09s), 같은 질의 글의 임베딩은 한 번만(`_query_memo`). fake·scoped 저장소도 같은 인자.
- `judge()` 는 차단 먼저, 그 안에서는 **입력 순서 유지**(유사도 재정렬 폐기). 입력이 유사도 순이면 종전과 같고, reranker 가 있으면 그
  순서가 알림 순서다. 유사도 값·임계치·키워드 조건은 그대로.
- `PrecheckOverlap.run()` → `PrecheckResult(alerts, related_research)`; `__call__` 은 종전처럼 알림 목록만(MCP·Streamlit·추천·차별화·
  비교표·측정 호환). 관련 연구는 REST `POST /v1/precheck` 응답 `related_research[]` 와 웹 ② 화면 "관련 연구" 목록(배지 "참고")에만.
- 차별화 추천(recommend_projects)·차별화 제안(differentiate)·`expected_similar` 채점(evaluate)은 알림 목록을 받으므로 자동으로 판정 후보
  집합을 따른다.

## 결과 (docs/eval-2026-10-28-precheck.md)
골든셋 10건 precheck 적중(상위 5 안 정답) 5/10(어제 코드, 오늘 코퍼스) → 9/10(후보 제한 + 자료원별 풀 + reranker 순서 유지).
남은 1건(03 도서관)은 어제와 같은 "주차 안내 과제 차단" — 판정 임계치 특성이지 이 변경의 대상이 아니다.
지연은 reranker 풀 크기에 비례하므로 풀 24건으로 2초 안을 겨냥했다(측정값은 평가 문서).

## 후속
- 자료원별 보장 수·풀 크기·관련 연구 k 는 표본이 쌓이면 `overlap.yaml` 에서 조정. 03 의 거짓 차단은 임계치·키워드 규칙의 몫.
- 관련 연구 목록을 선행연구 브리핑(`/new/brief`)과 합칠지는 사용성 검토 뒤.
