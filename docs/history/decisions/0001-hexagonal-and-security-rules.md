# ADR 0001 — 헥사고날 구조와 보안 규칙 A~J (2026-09-08)

**배경** 수집 문서·LLM 출력·외부 파일은 전부 비신뢰다. 로컬 LLM(mlx-lm)·DB(SQLite)·양식(HWPX)은 바뀔 수 있다.
**선택지** (a) 단일 스크립트 + 서비스 모듈, (b) 계층형(MVC), (c) 헥사고날(포트·어댑터).
**결정** (c). domain 은 순수 파이썬, application 은 포트(`typing.Protocol`)만, adapters 만 외부 라이브러리, entrypoints 는 호출만.
import-linter 계약(현재 8건)으로 강제. 보안 규칙 A(비신뢰 텍스트·JSON 만 파싱·근거 id 대조) ~ J 를 CLAUDE.md 에 고정.
**이유** 유스케이스를 fake 로 테스트할 수 있고(LLM·DB 없이), 어댑터 교체(모델 비교·DB 전환)가 포트 뒤에서 끝난다.
**결과** 테스트 1,178건이 LLM·임베딩 없이 돈다. 2026-10-23 구조 검토에서도 유지(ADR 0002). 근거 `609e2e4`, `docs/architecture.md §1~§3`.
