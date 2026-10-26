# ADR 0014 — PR 은 CI 통과 뒤 자동 병합 (2026-10-26, PR #17)

**배경** 하루에 PR 10건 이상을 사람이 하나씩 확인·병합하는 흐름이 병목.
**선택지** (a) 사용자가 확인·병합, (b) CI 통과 뒤 자동 병합(본인 PR 만), (c) 보호 규칙 없이 main 직접 푸시.
**결정** (b). 작업마다 main 에서 브랜치 → 검사 → PR → `gh pr checks --watch` → `gh pr merge --merge --delete-branch` → main 재검사. 검사 실패·충돌·리뷰 필요면 멈추고 보고. 동료 PR 은 손대지 않는다. 경과 기록(timeline·metrics·ADR)을 병합 전에 남긴다.
**이유** CI(backend·detect)가 로컬 검사와 같은 명령을 돌려 검증 기준이 같다.
**결과** #17~#19 가 이 흐름으로 병합. 보호 규칙 권장값은 `docs/status.md §5`.
