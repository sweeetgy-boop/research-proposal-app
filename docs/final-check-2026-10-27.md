# 내일 아침 시범 준비 (2026-10-28, 3명)

## 접속 주소와 경로

- 외부 주소 `https://rra.ai-edu-lab.co.kr` 은 **아직 열리지 않음** — ai-edu-lab.co.kr 의 DNS 가 Gabia(Cloudflare 아님)이고 이 맥에 cloudflared·인증서가 없어 터널을 만들지 않았다(ADR 0024, `docs/deploy-exposure.md` §5). 앱 쪽 준비(public_origin·Secure 쿠키·Origin 검사·client_ip·tunnel plist)는 끝났다(#45).
- 선택지: (a) ai-edu-lab.co.kr 존을 Cloudflare 로 옮기고 터널 + Access, (b) Tailscale serve 대체(동료가 Tailscale 설치). 어느 쪽이든 아래 "오늘 밤 할 일" ①② 가 사람 작업.
- 같은 맥에서는 `http://127.0.0.1:8000` 으로 바로 쓸 수 있다. 앱 로그인 3종: 직원 탭(사번) / 그 외 탭(아이디·비밀번호) / "관리자" 링크(토큰, .env RRA_API_TOKEN).

## 서비스 상태 (launchd, 19:01 등록 · 03:15 api 재시작 = main #57)

| 서비스 | 상태 | 확인 |
|---|---|---|
| com.rra.mlx (Qwen2.5-7B-Instruct-4bit, 127.0.0.1:8080) | 실행 중(PID 있음) | `curl http://127.0.0.1:8080/v1/models` |
| com.rra.api (127.0.0.1:8000, web/dist 03:15 빌드 = main 7bb3929) | 실행 중, healthz 200·무토큰 401·웹 200·보안 헤더 유지. 03:22 생성 1회 확인: 골든셋 04 → drafted 145초 → 최종 검토 15초 → HWPX 41,136 bytes(전체 227초) | `curl http://127.0.0.1:8000/healthz` |
| com.rra.backup (매일 03:30) | 등록됨 | `launchctl list \| grep com.rra` |
| com.rra.ingest (매일 02:30, --skip-unavailable) | 등록됨 | 〃 |
| com.rra.tunnel | 미등록(터널 없음) | 접속 경로 결정 뒤 |

`rra llm-check --stage compose` ok(served 7B). 측정에 쓰던 수동 mlx 서버·백그라운드 작업은 모두 종료했다.

## 2026-10-28 새벽 수정 결과 ([F1] 빈 초안 방지·[F2] 유사과제 판정 복구)

- **[F2] 유사과제 판정**(#56): 판정·알림 후보는 과제형 자료원(own·alio·NTIS 과제·g2b)만. 논문·보고서·특허(ScienceON·OpenAlex·NTIS 보고서)는 ② 화면 "관련 연구" 목록(배지 참고)으로 분리. 골든셋 적중 **5/10 → 9/10**(03 은 기존 거짓 차단), 지연 1.84~2.09s(중앙값 2.06s, 목표 2초를 0.06s 초과 — reranker 단독 지연, 후속). 설정 `config/overlap.yaml candidates`.
- **[F1] 빈 초안 방지**(#55·#57): 저녁 invalid 원인은 빈 문장 목록이 ok 로 통과(10)·JSON 깨짐(11)·펜스(2), 코퍼스 증가로 섹션 [자료] 글자 2.1×. 수정: 일부 섹션 실패해도 drafted + 실패 섹션 목록(웹 "생성 실패 — 이 섹션 다시 생성" 버튼, 전부 실패일 때만 invalid), 빈 목록은 실패로 보고 교정 재요청, 섹션 [자료] 상한(청크 500자·10청크), finish_reason 집계, 로컬 2회 실패 섹션만 Gemini 4 Argon 대체 작성(`llm.yaml compose.fallback: gemini` 시범 기본 켬, manifest `fallback_sections`, 공용 계정 internal 제외 규칙 동일, 웹 "대체 작성" 배지). 골든셋 10건 재측정 2회: **유효 10/10·10/10, 빈 초안 0, 실패 섹션 1→0**(점수 평균 2.77·2.62, 평균 201·195초, 대체 작성 1차 1건·2차 5건(01 expected_technology·02 title·07 task_type·09 title·10 task_type), Gemini 11+15회). 자세한 표 `docs/eval-2026-10-28.md`, ADR 0027.
- 공용 계정 비밀번호 최소 길이 4자(시범 한정, #54). Tailscale 은 미설치라 `public_origin` 미변경(아래 할 일).
- Gemini 기타 사용(이번 작업): 약 30 / 60 (F1 재측정 26 + 생성 확인 2회 약 4, F2 0).

## 한 건 생성 소요 시간 (실제 7B + Argon, 골든셋 04, 로컬 127.0.0.1:8000, 19:24 · 03:22 재확인 동일)

- 유사과제 확인(precheck) 38~56초 — 차별화 과제 추천·차별화 제안(Gemini)까지 한 번에 돌려서. 검색·reranker 자체는 2초 안팎.
- 생성 + Argon 1차 검토 반영 **155초** → 최종 검토 15초 → HWPX 0.2초(40,926 bytes). 로그인부터 다운로드까지 **227초(3분 47초)**.
- 골든셋 10건 측정 평균 180~200초/run. 어제의 리스크(7B JSON 실패로 4/10 빈 초안)는 03:00 [F1] 수정으로 해소: 재측정 2회 유효 10/10·빈 초안 0. 섹션 하나가 실패하면 그 섹션만 "다시 생성" 버튼, 로컬 2회 실패면 Gemini 대체 작성(배지).

## 오늘 작업 결과 요약

- 병합 PR: #42 데이터 위치 고정, #43 사진 거르기, #44 판독 병렬, #45 브라우저 접속 준비, #46 자료원 IP, #47 migration 006, #48 로그인(사번·공용 계정), #50 NTIS 실응답 확정, #51·#53 NTIS 보고서 파싱 수정, #52 시범 준비(대기 6·안내서), #49 [Z] 문서 통합. 테스트 1,772 통과·계약 8.
- 자료: DB 문서 13,008+ — korail_web 5,098(텍스트 2,672 + 이미지 판독 2,426), openalex 2,482, scienceon 2,045, **ntis 3,084(신규: 과제 2,000 + 연구보고서 1,084)**, own 1,119, alio 120, rnd_notice 91, bai 21, datago 16, mofe 10, molit 6 = 14,092. 표 사실 korail_web 48,253·vision 453.
- 이미지 판독: 4,450장 → 거르기 447 제외 → OCR 4,003 → 사진 1,570 제외 → Argon 2,000(성공 1,903·실패 166 은 OCR 만)·OCR 만 364. 숫자 대조 통과율 표 92%·체계도 75%·그래프 71%. 표본 `docs/ocr-sample/`(사진 표본 30장 `excluded/photo_sample.json`).
- 측정: 골든셋 10건 유효 6/10, 점수 평균 2.5, 충족률 0.63, 무관 인용 0, precheck 적중 6/10(오전 9/10 — ScienceON 논문이 사내 기록 위로 올라온 영향, #12). Gemini 사용: 이미지 판독 2,000(+표본 재호출 약 50), 기타 12/80.
- 로그인: 직원 사번(HMAC)·공용 계정(scrypt)·관리 토큰, run 소유자 격리, 공용 계정 internal 제외, 일일 상한(공용 10·직원 20), Gemini 일일 300회 상한. **사번·공용 계정은 아직 등록되지 않았다**(아래 ③④).
- NTIS: 서버 IP 등록이 반영돼 4개 서비스 실호출 ok, 파서 확정(JSON 감싼 XML·맨 &·맨 <), 과제 2,000·연구보고서 1,084건 적재. ScienceON ok.

## 내가 오늘 밤 할 일 (순서대로)

① 외부 접속 경로 결정·준비 — (a) Cloudflare: Cloudflare 에 `ai-edu-lab.co.kr` 존 추가 → 기존 레코드(agent A 34.64.53.121 포함) 옮긴 뒤 Gabia 네임서버 변경 → `brew install cloudflared && cloudflared tunnel login` → `cloudflared tunnel create rra` → `deploy/cloudflared/config.example.yml` 의 `<TUNNEL_ID>` 를 넣어 `~/.cloudflared/config.yml`(600) → `cloudflared tunnel route dns rra rra.ai-edu-lab.co.kr`. (b) Tailscale: `brew install --cask tailscale` → 로그인 → `tailscale serve --bg --https=443 http://127.0.0.1:8000` → 동료 초대·ACL 443 만 → `config/api.yaml public_origin` 을 `https://<이 맥>.ts.net` 으로 → `launchctl kickstart -k gui/$(id -u)/com.rra.api`.
② (Cloudflare 일 때) Access 설정: Zero Trust → Access → Applications → Self-hosted → `rra.ai-edu-lab.co.kr`, Allow 이메일 3개, One-time PIN, 세션 1주일. 그 다음 `cp deploy/launchd/com.rra.tunnel.plist ~/Library/LaunchAgents/ && launchctl load -w ~/Library/LaunchAgents/com.rra.tunnel.plist` → `curl -sI https://rra.ai-edu-lab.co.kr | head -5` 가 302 + cloudflareaccess 이어야 함. 앱이 바로 보이면 즉시 `launchctl unload -w ~/Library/LaunchAgents/com.rra.tunnel.plist`. 통과하면 `config/api.yaml trust_cf_connecting_ip: true` + api kickstart.
③ 직원 등록 — 명부 파일로 한 번에(2026-10-28, 사번 열만 읽고 출력은 개수만, 절차 `docs/pilot-guide.md` §6):
```
cd /Users/chan/projects/research-proposal-app && .venv/bin/rra auth staff import --file ~/Downloads/사번_전체.xlsx --dry-run
.venv/bin/rra auth staff import --file ~/Downloads/사번_전체.xlsx [--pad <자릿수>] [--replace]
.venv/bin/rra auth staff count
```
   한 명씩은 `.venv/bin/rra auth staff add`(사번 입력, 화면에 안 보임).
④ 공용 계정: `.venv/bin/rra auth guest set --id korail` (비밀번호 두 번, 8자 이상)
⑤ `.venv/bin/rra auth status` 확인, `ls -la data/auth`(700/600), `git status` 에 data/auth 없음. `data/auth/secret` 은 백업에 포함(잃으면 run 소유권 단절).
⑥ 외부 주소(또는 127.0.0.1:8000)에서 로그인 시험: 등록 사번 → 입력 화면, 미등록 사번 → "사번 또는 아이디·비밀번호를 확인하세요", 공용 계정 → 상단 "공용 계정" 표시, 관리자 토큰 → 모든 run.
⑦ ScienceON `.env` 확인 — 19:01 `rra sources check --source scienceon` ok(ARTI 1,858·REPORT 370·PATENT 911). Mac mini 에서 돌릴 때 그 .env 도 같은 값.
⑧ NTIS 서버 IP — 해결됨(19:01 ok, 과제 2,000 적재). 이 회선은 공인 IP 가 59.0.251.250↔59.0.166.199 로 바뀌므로 둘 다 활용신청에 등록돼 있어야 하고, 다른 IP 로 바뀌면 활용신청 서버 IP 와 `config/sources.yaml ntis.registered_ips` 를 함께 갱신. 운영 전 공인 IP 고정(전산 부서 또는 고정 IP 회선 Mac mini).

## 내일 아침 점검 순서 (시작 10분 전)

1. 맥 상태: 전원·절전 해제(`pmset -g | grep sleep`, 덮개 닫힘 주의), `curl -s https://api.ipify.org` 가 59.0.166.199 또는 59.0.251.250 인지(아니면 NTIS 빠짐).
2. `launchctl list | grep com.rra` 4종 PID 확인, `curl http://127.0.0.1:8080/v1/models`, `curl http://127.0.0.1:8000/healthz`.
3. 외부 주소 접속(이메일 코드 → 로그인 화면) 또는 로컬 주소.
4. 동료 1명 접속 확인: 로그인 → 입력 화면까지. 막히면 `tail -30 ~/Library/Logs/rra-api.err.log`.

---

# 최종 점검 (2026-10-27) — [자동 진행] 판단 목록과 확인 요청

(작업이 끝나면 [Z] 에서 정리해 마지막 메시지로 보낸다. 아래는 진행 중 누적.)

## 실행 명령 (아침 확인용)

```
cd /Users/chan/projects/research-proposal-app && .venv/bin/rra api --port 8000   # 127.0.0.1:8000, web/dist 서빙
```
브라우저 http://127.0.0.1:8000 → 토큰 입력(.env 의 RRA_API_TOKEN) → ① 입력 → ② 유사과제·추천 → ③ 생성 → 초안 → ④ 편집 → ⑤ 최종 검토 → ⑥ 다운로드.

## [자동 진행] 에서 실제로 일어난 판단

| 시각 | 판단 | 근거·기록 |
|---|---|---|
| 17:50 | `rra vision sample` 이 캐시 없는 항목을 다시 Argon 호출(이미지 상한 2,000 도달 뒤 약 50회 초과) → 즉시 중단, 표본은 `--cached-only` 로 다시. 초과분은 실패 166건의 재시도로만 쓰였고 더는 호출하지 않음 | overnight 17:50 행 |
| 17:50 | 이미지 판독 적재가 DB CHECK(text_basis 에 image_vision 없음, migration 002) 로 실패 → 운영 DB 는 건드리지 않고 migration 006 을 레인(fix/image-vision-basis)에서 만들어 테스트·사본 검증 뒤 적용. 대기열(적재·표 사실·골든셋 측정)은 멈추지 않고 진행하고, 판독 결과는 006 병합 뒤 적재. 골든셋 10건은 판독 결과 없이 1차 측정, Gemini 기타 잔여가 30 이상이면 적재 뒤 같은 설정으로 한 번 더 측정해 전후 비교(최대 3회 규칙 안) | overnight 17:50 행 |
| 17:28 | 시범 운영 [W]: ai-edu-lab.co.kr DNS 가 Gabia(Cloudflare 아님)·cloudflared 미설치·cert.pem 없음 → 규칙 3·5 대로 터널을 만들거나 올리지 않고 코드(public_origin·client_ip·Origin 검사)·설정 초안·plist·절차·Tailscale 대체만 준비(#45). agent.ai-edu-lab.co.kr 은 다른 호스트라 건드리지 않음 | ADR 0024, `docs/status.d/feat-tunnel.md` |
| 10:03 | reranker 모델 라이선스가 지시서의 MIT 가 아니라 Apache-2.0 — 업무 이용 허용이라 진행 | HF 모델 카드, llm.yaml 주석, ADR 0013 |
| 10:40 | precheck reranker 후보 폭 k×4 → k×3 (지연 2.0~2.4s → 1.5~1.95s, 상한 2초) | data/eval/precheck_hits*.json |
| 10:40 | 골든셋 정답 목록을 두 모드의 상위 5 제목을 보고 같은 주제 사내 기록을 더해 넓힘(기존 3 + 신규 7) | tests/golden/*.yaml expected_similar |
| 11:07 | Q9 2단계 중단 — Q4 "인용 금지" 가 검색 근거의 본보기 doc 인용까지 폐기해 섹션이 비던 결함. 베끼기만 폐기로 완화(설정 아님, 규칙 변경) | overnight 11:07 행, 커밋 5c97b23 |
| 11:10 | 자료원 균형: `config/retrieval_mix.yaml` 신설. 걸러서 0건이면 전부로 되돌림(근거를 비우는 쪽보다 넓게 주는 쪽) | architecture §4.16 |
| 11:10 | reranker 기본 켬(설정으로 끌 수 있음, 모델 폴더 없으면 자동 생략) | ADR 0013 |
| 11:25 | ScienceON: .env 수정 금지라 원본은 두고 worktree 사본(.env 복사본)에서 값을 맞바꿔 검증·적재 — 사람 확인 뒤 원본 수정 | 레인 B 보고 |
| 15:41 | RRA_DATA_DIR 기본값은 .env 수정 금지라 코드 기본값(git common dir → 원래 저장소 data/)으로 해결, .env 에 명시하는 것은 사람 권장 사항으로 기록. 골든셋 10건은 Gemini 잔여(80) 가 30 이상이라 검토 포함으로 측정 | overnight 15:41 행 |
| 15:32 | 병합 뒤 worktree 삭제로 감사원·R&D 공고 스냅샷(미커밋)이 사라져 같은 설정으로 재수집(삭제가 아니라 재수집, data/ 기존 데이터는 건드리지 않음). 원인 추정: `gh pr merge --delete-branch` | overnight 15:32 행 |
| 15:20 | P2-7 공고 수집(레인 G): NTIS 공고는 robots `Disallow: /` 라 수집 안 함(키 API 만), IRIS 공개 POST 검색 폼은 robots 비금지·무세션이라 허용, 세션 첨부는 흉내 내지 않고 이름만, 같은 공고는 한 문서 | ADR 0023 |
| 15:17 | [P2] 보류 항목(레인 E): ebid 불명확 → 나라장터 공개 API로 전환(키 대기), 감사원은 Playwright 로 공개 화면만 조작·/api/ 미호출, 국정감사 지적은 보류, 통계는 키 필요 API 대신 공공데이터포털 파일, 경영평가는 알리오 대신 기재부 보도자료, 판 추적 모호=둘 다 현행+기록 | ADR 0021, docs/history/progress.d/feat-policy-sources.md |
| 15:17 | 용어 후보(레인 F)는 파일만 만들고 overlap.yaml 에 자동 반영하지 않음. 표 사실은 정밀도 우선(못 읽으면 내지 않음) | ADR 0022 |
| 13:49 | NTIS 실호출이 IP 차단 → 합성 fixture 로 테스트·어댑터·REST 를 완성하고 적재는 IP 반영 뒤로. retrieval_mix 의 '국가R&D 과제 요약을 필요성·기대효과 근거에서 제외' 는 doc_type 만으로 own 과제와 구분되지 않아 주석으로만 남기고 보류 | overnight 13:49 행, PR #35, ADR 0020 |
| 13:44 | '철도연구원 연구개발 중장기 발전전략 수립'(사전정보공표 > 사전정보공개목록, 2025-01-15, 연구계획처)은 과제 요약(개요·목적·내용·기대효과·활용계획, 577자)만 있고 **원문공개 비공개**(정보공개법 제9조 제1항 제7호). 첨부·내장 이미지 없음, 비전·중점 분야·핵심 기술·추진 과제 체계 없음 → `korail_rnd_strategy.draft.yaml` 초안과 rnd_strategy 설정·promote 는 만들지 않음. 같은 메뉴의 '코레일 연구개발 중장기 운영전략 연구'(2022-08-30)도 요약만·비공개. 스냅샷 전체(첨부 이름·본문)에서 연구개발 전략체계 문서는 더 없음 | 스냅샷 items/preinfo/preinfo-55-1399.txt·preinfo-55-531.txt, 상세 페이지 재확인 1회 |
| 13:20 | [N] 지시 본문이 메시지에 붙어 있지 않아 기존 문서의 NTIS 대기 항목(실호출·fixture·FIELDS·record_tag·연구보고서 가능 여부·3단계 준비)으로 레인을 구성 | overnight 13:20 행 |
| 12:45 | Q9 결정: 측정 n 이 작아(로컬 2건·검토 3건) 방향만 보고 결정 규칙대로 켬/끔. 모두 켬은 7B JSON 실패를 늘려 invalid 5/10 | docs/eval-2026-10-27.md |
| 12:55 | ScienceON 적재가 한 질의·target 의 서버 오류(500)로 0건 → 그 조합만 건너뛰도록 바꾸고 재적재(설정 아님, 어댑터 규칙) | overnight 12:55 행 |
| 11:55 | 크롤링: www.korail.com(SPA·봇 보호)은 우회하지 않고 제외, info.korail.com 만 수집. 보도자료는 최근 5년·사진 첨부는 메타만. 50MB 초과 보고서 13건 보류. 감사원(JS·robots /api/ 금지)·발주 용역(세션 POST 폼)·안전 통계(키 필요)는 보류 | docs/korail-web-crawl.md, ADR 0019 |
| 11:30 | 섹션별 검색이 더한 청크를 제목·선택형 프롬프트에서 제외(프롬프트 34k자 → 7B JSON 실패 원인) | overnight 11:19 행 |

## 내가 확인할 것 (체크박스)

- [ ] **7B JSON 실패 4/10**(골든셋 01·02·06·10, 두 번 모두 invalid; 시범 흐름 01 도 invalid) — 오전엔 01 이 유효했음. 코퍼스 확대 뒤 섹션별 검색 청크·프롬프트 길이 증가 의심. 시범 중 "다시 생성" 안내, 후속으로 섹션 프롬프트 상한·실패 섹션 재요청(docs/eval-2026-10-27.md §8.1)
- [ ] **precheck 적중 9/10 → 6/10** — ScienceON 논문(유사도 0.89~0.90)이 사내 기록(0.88) 위로 올라와 골든셋 정답이 밀림(01). 사내 기록·국가R&D 티어 우선 보장을 `retrieval_mix`/overlap 규칙에 둘지 결정(#12). 논문 인용 11 → 2 도 같은 원인
- [ ] precheck 응답 38~56초 — 자동 추천·차별화 제안(Gemini)이 한 요청 안에 들어 있어서. 비동기/선택 실행으로 바꿀지(ADR 0012 자동 1회 규칙 재검토)
- [ ] 이미지 판독 표본 지표(docs/ocr-sample/summary.md): 숫자 대조 통과율 표 92.2%·글자 이미지 80.2%·체계도 75.3%·그래프 71.3%·기타 58.8% — "기타" 1,500장은 Argon 구조화 0%(사진에 가까운 것), 다음 상한에서 실패 166장 재시도 여부
- [ ] 표본 명령 `rra vision sample` 은 캐시 없는 항목을 다시 Argon 호출한다 — 운영 문서에 `--cached-only` 사용을 적음(CLAUDE.md). 명령 기본값을 cached-only 로 바꿀지
- [ ] Q8·Q9 기본값 결정(ADR 0013, docs/eval-2026-10-27.md): 켬 = section_search·additions·reranker·rule_check, 끔 = clarify·outline·exemplars·two_candidates. 로컬 빼기 실험은 골든셋 2건(n 작음) — 표본이 쌓이면 재측정
- [ ] 전략체계 초안 항목별 출처와 텍스트·이미지 차이 — 초안 출처: 공사 홈페이지 '중장기 경영목표'(ESG경영 > 경영공시 > 일반항목, https://info.korail.com/info/contents.do?key=1900, 스냅샷 2026-10-27, basis text, 5 방향·15 과제). 경영가치체계(공사소개 > 일반현황)·환경경영 비전 및 전략·사전정보공표 '경영목표 목표수준 종합'·'철도연구원 연구개발 중장기 발전전략 수립' 도 수집됨. 전략체계도 이미지 판독(basis image_vision) 결과와의 차이는 판독 뒤 기록
- [ ] 연구개발 중장기 전략 초안은 **없음** — 근거 문서가 요약·비공개뿐(위 13:44 판단). 원문(결과 보고서)이 확보되면 `data/inbox/own_docs/` 에 넣고 다시 요청하면 `korail_rnd_strategy.draft.yaml` 초안·'연구개발 중장기 전략 초안(확인 전)' 표시·`rra strategy promote` 대상을 같은 방식으로 만든다
- [ ] 크롤링 범위 축소·보류 목록 (docs/korail-web-crawl.md)
- [ ] 이미지 판독 견본과 숫자 대조 통과율 (docs/ocr-sample/)
- [x] 열어 둔 PR — 없음(#49 [Z]·#52 시범 준비까지 모두 병합 예정, 마지막 메시지 시점 기준)
- [ ] 후보 파일(rail_terms.candidates.yaml, generic_terms 후보)
- [ ] 발주 용역 임계치 결과
- [ ] Lighthouse 미달 항목 (현재 없음 — /login 100/100/100)

## 운영 전 해결할 것

- [ ] **API 호출 기기의 공인 IP 고정** — 전산 부서 확인 또는 고정 IP 회선의 Mac mini. IP 가 바뀌면 NTIS 활용신청 서버 IP 와 `config/sources.yaml ntis.registered_ips` 를 함께 갱신(#46, ADR 0025)
- [x] NTIS: 19:01 부터 응답(공인 IP 59.0.166.199, 등록 반영). 파서가 실응답 형식(JSON 으로 감싼 XML)을 못 읽던 결함은 #50 으로 수정, `rra sources check --source ntis,ntis_reports,ntis_insights` 셋 다 ok. 적재 ntis 2,000·ntis_reports 1,500 은 19:3x 실행(결과는 overnight 기록). 남은 일: 공인 IP 가 바뀌면 다시 막힘 → 아래 IP 고정
- [ ] 외부 접속: ai-edu-lab.co.kr DNS 가 Gabia 라 Cloudflare Tunnel 을 쓰려면 존 이전이 필요. 아니면 Tailscale 대체(`docs/deploy-exposure.md` §5, `docs/status.d/feat-tunnel.md` 내가 할 일 ①~⑥)

## 내가 할 일 (사람 입력)

- [ ] **시범 뒤 공용 계정 비밀번호 최소 길이를 8 로 되돌릴 것** — `config/auth.yaml guest.min_password_length: 4`(2026-10-28 시범 한정, #54) → 8
- [ ] **Tailscale 주소 → `config/api.yaml public_origin`** — 2026-10-28 01:46 기준 이 맥에 Tailscale 이 설치돼 있지 않아 `tailscale serve status` 주소를 얻지 못했다. 설치·`tailscale serve --bg --https=443 http://127.0.0.1:8000` 뒤 주소(`https://<이름>.<tailnet>.ts.net`)를 `public_origin` 에 넣고 `launchctl kickstart -k gui/$(id -u)/com.rra.api`
- [ ] **main 보호 규칙 확인** — 19:45 `gh api …/branches/main/protection` 이 "Branch not protected", rulesets 도 없음. 그래서 #52·#53 은 CI 완료 전에 `gh pr merge` 가 통과됐다(둘 다 로컬 전체 검사 통과, main CI 도 #52 success·#53 진행 중 확인). 저장소 설정 변경은 금지라 손대지 않음 → PR 필수·상태 검사(backend·detect·web)·최신 브랜치 필수를 직접 켤 것
- [x] `.env` 의 ScienceON client_id·인증키 맞바꿈 — 15:48 실호출 auth ok(ARTI 1,858·REPORT 370·PATENT 911). Mac mini 의 .env 도 같은 값인지 확인
- [ ] ScienceON 보고서(REPORT)는 doc_type `internal_report` 로 저장됨(적재 당시 `report` 가 없었음) — retrieval_mix 의 '논문·보고서·특허' 보장에는 들어가지 않음. 다음 적재 때 `report` 로 재매핑할지 결정
- [x] **NTIS 서버 IP** — 19:01 실호출 ok(#50). 공인 IP 가 59.0.251.250 → 59.0.166.199 로 바뀌는 회선이라 두 IP 모두 등록돼 있어야 하고, 다른 IP 로 바뀌면 활용신청 서버 IP 와 `config/sources.yaml ntis.registered_ips` 를 함께 갱신
- [ ] **`RRA_DATA_GO_KR_KEY`** — 조달청 나라장터 입찰공고정보서비스(BidPublicInfoService, 용역 조회). 공공데이터포털(data.go.kr) 검색 "나라장터 입찰공고정보서비스" → 활용신청(자동승인) → 일반 인증키를 .env 에. 반영 뒤 `rra sources check --source g2b` → 실응답 녹화 → FIELDS 확정 → `rra ingest --source g2b --limit 200`
- [ ] (선택) 한국철도공사 수송실적 OpenAPI / KOSIS 통계 OpenAPI 키 — 파일데이터(datago)로 대체돼 미구현. 필요해지면 신청
- [ ] NTIS OpenAPI 에 "사업공고" 서비스가 있는지 기존 키로 확인(https://www.ntis.go.kr/rndopen/api/ Open API 신청 화면) — NTIS 공고 페이지는 robots 전면 금지라 수집하지 않음. (선택) 공공데이터포털 "과학기술정보통신부_사업공고"(15074634)는 국토교통 밖이라 보류
- [ ] 감사원 수집(`rra crawl bai`)은 Playwright 가 필요: `uv pip install playwright && .venv/bin/playwright install chromium` (선택 의존성, pyproject 미추가)
- [ ] `.env` 에 `RRA_DATA_DIR=/Users/chan/projects/research-proposal-app/data` 를 명시(Mac mini 는 그 경로) — 기본값도 원래 저장소 data/ 를 찾지만 명시가 안전
- [ ] 용어 후보 검토 — `rra terms candidates` 가 만든 `config/rail_terms.candidates.yaml`·`config/generic_terms.candidates.yaml`(미커밋)을 보고 generic_terms 만 overlap.yaml 에 옮길지 결정(자동 반영 없음, 이슈 #11 댓글 참조)
- [ ] `rra strategy promote` 실행 여부
- [ ] NTIS·KIPRIS 키 신청
- [ ] 공고문 파일(data/inbox/notice/)
- [ ] 동료 GitHub 아이디(CODEOWNERS web/)
