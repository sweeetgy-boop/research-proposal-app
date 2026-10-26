# 기여 방법

## 흐름
1. `main` 에서 기능 단위의 짧은 브랜치를 만든다. 이름 규칙: `feat/<무엇>`, `fix/<무엇>`, `chore/<무엇>`, `docs/<무엇>`.
2. 로컬 검사 통과 → 커밋 → push → PR. PR 템플릿(`.github/pull_request_template.md`)을 채운다.
   ```bash
   pytest -q && lint-imports && ruff check src tests      # backend
   cd web && npm run lint && npm run typecheck && npm test  # web (있을 때)
   ```
3. CI(`.github/workflows/ci.yml`: `backend`, `web`)가 통과하면 합친다(squash 금지, merge commit). 합친 뒤 브랜치는 지운다.
4. 다음 작업이 앞 PR 에 의존하면 앞 PR 이 합쳐진 뒤 `main` 에서 새 브랜치를 만든다.
5. **경과 기록(`docs/history/`)** — 합치기 전에 반드시:
   - `docs/history/timeline.md` 에 항목 하나(날짜, 무엇을, 왜, PR 번호, 핵심 수치).
   - 수치(테스트 수·자료원 건수·생성 시간·점수 등)가 바뀌었으면 `docs/history/metrics.csv` 에 행 추가
     (`tools/history_charts.py` 로 그래프 재생성).
   - 주요 결정(모델·구조·임계치·흐름)은 `docs/history/decisions/NNNN-<slug>.md` 에 ADR(배경·선택지·결정·이유·결과).
   - 화면이 바뀌었으면 `docs/history/screens/<YYYY-MM-DD>-<화면>.png` 캡처.

## 동료 PC 준비 (백엔드 없이 프론트엔드만 개발할 때)
```bash
git clone <저장소> && cd research-proposal-app
uv venv --python 3.12 && uv pip install -e ".[dev]"     # 임베딩·모델 없이 돈다
cp .env.example .env && chmod 600 .env                   # RRA_API_TOKEN 만 채운다 (openssl rand -hex 32)
RRA_FAKE_LLM=1 .venv/bin/rra api                         # 가짜 LLM·메모리 저장소. 127.0.0.1:8000
cd web && npm install && npm run dev                      # 프론트엔드 (있을 때)
```
가짜 모드에서는 precheck·생성·검토·마무리가 모두 가짜 응답으로 즉시 돌아온다. 실제 모델·DB 는 Mac mini 에만 있다.
REST 스키마는 `docs/openapi.json` (`rra api schema` 로 생성), 세션 쿠키·CSRF 는 `deploy/README.md` §4.

## API 변경
- 요청·응답 필드가 바뀌어야 하면 **먼저 Issue** 로 올린다(어느 화면이 무엇을 필요로 하는지).
- 백엔드 PR 이 `docs/openapi.json` 을 바꾸면 PR 본문 "프론트엔드 영향" 에 **명시**한다. 프론트엔드는 그 PR 이 합쳐진 뒤 맞춘다.
- 청크·제안서 본문·검토 의견은 수집 자료·LLM 출력(비신뢰 텍스트)이다. 화면에 그대로 HTML 로 넣지 않는다.

## 비밀·데이터
- `.env`, 접속 토큰, API 키(Gemini·ScienceON·NTIS·KIPRIS), 기기 MAC 은 **공유 금지** — 채팅·이슈·PR·커밋에 넣지 않는다.
- `data/`(DB·inbox)·`runs/`·실물 양식 `config/templates/proposal_korail.hwpx` 는 커밋하지 않는다(.gitignore).
- PR 본문·이슈에 사내 과제명·제안자 이름을 적지 않는다(건수·구조만).

## 코드 규칙 (백엔드)
- 헥사고날 계층(`CLAUDE.md`, `docs/architecture.md` §1). `lint-imports` 계약 8건이 강제한다.
- 새 기능은 domain → ports → usecase(fake 로 테스트) → adapter. 테스트는 LLM·임베딩·네트워크 없이 돌아야 한다(`tests/fakes.py`).
- 키 값·원문은 로그·manifest·테스트 fixture 에 남기지 않는다(보안 D·I).
