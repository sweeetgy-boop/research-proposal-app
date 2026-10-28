# 배포 기록 (시범 운영, 2026-10-28 ~)

- `tools/deploy.sh` 가 배포마다 `<YYYY-MM-DD-HHMM>.md` 를 만든다(커밋·반영 PR·web 빌드 여부·run 대기·healthz·로그인 화면·외부 주소).
- `pending.md` — **반영 대기 PR 목록**. 시범 기간에는 PR 을 main 에 합쳐도 운영 API 를 자동 재시작하지 않고 여기에 한 줄 쌓는다.
  운영자가 "배포해" 하면 `tools/deploy.sh` 가 이 목록을 그날 기록으로 옮기고 비운다.
- 예외: 보안 수정, 로그인·접속이 막히는 오류 수정은 합친 즉시 `tools/deploy.sh` 로 반영하고 운영자에게 알린다.
- 절차·규칙: `docs/pilot-guide.md` §6.3, `deploy/README.md` §4.
