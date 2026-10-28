#!/usr/bin/env bash
# 시범 운영 배포 (2026-10-28) — main 의 현재 커밋을 운영 API(launchd com.rra.api)에 반영한다.
#
#   tools/deploy.sh [--wait [--wait-max SEC]] [--force] [--no-build] [--no-external] [--dry-run]
#
# 순서:
#   1. main 최신 확인 — 브랜치 main, 추적 파일 변경 없음, origin/main 과 같은 커밋 (아니면 중단)
#   2. web/ 이 지난 배포 이후 바뀌었으면(또는 web/dist 가 없으면) `npm run build`
#   3. 대기·실행 중인 생성 run 확인 (`rra runs active --json`) — 있으면 --wait 는 끝날 때까지 기다리고,
#      --force 는 무시하고, 둘 다 없으면 중단
#   4. data/deploy/version.json 기록 (커밋·시각·반영 PR) → `launchctl kickstart -k gui/$(id -u)/com.rra.api`
#   5. 확인 — 127.0.0.1:8000/healthz 의 version.commit 이 HEAD 인지, /login 이 200 인지, 외부 주소 /healthz,
#      Tailscale `funnel status` 에 "(Funnel on)" 이 있는지(읽기만 — serve/funnel 설정은 절대 바꾸지 않는다).
#      주의: 이 맥은 tailnet 안이라 외부 주소 확인은 내부 경로로 간다 — Funnel 이 꺼져도 ok 로 보일 수 있어
#      Funnel 확인을 따로 한다. 인터넷 쪽 확인은 docs/pilot-guide.md "접속이 안 될 때".
#   6. docs/history/deploys/<시각>.md 기록, pending.md(반영 대기 PR 목록) 비움
#
# 규칙(docs/pilot-guide.md §6.3): 시범 기간에는 PR 을 합쳐도 자동으로 재시작하지 않는다. 반영할 PR 은
# docs/history/deploys/pending.md 에 쌓아 두고 운영자가 "배포해" 하면 이 스크립트로 반영한다. 보안 수정·
# 로그인/접속이 막히는 오류 수정은 바로 반영한다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RRA="$ROOT/.venv/bin/rra"
PY="$ROOT/.venv/bin/python"
DATA_DIR="${RRA_DATA_DIR:-$ROOT/data}"
VERSION_FILE="$DATA_DIR/deploy/version.json"
LABEL="com.rra.api"
LOCAL_URL="${RRA_DEPLOY_LOCAL_URL:-http://127.0.0.1:8000}"
EXTERNAL_URL="${RRA_DEPLOY_EXTERNAL_URL:-https://rra.taile5afcf.ts.net}"
TAILSCALE="${RRA_TAILSCALE_BIN:-/Applications/Tailscale.app/Contents/MacOS/Tailscale}"
DEPLOY_DIR="$ROOT/docs/history/deploys"
PENDING="$DEPLOY_DIR/pending.md"

WAIT=0; WAIT_MAX=1800; FORCE=0; BUILD=1; EXTERNAL=1; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --wait) WAIT=1 ;;
    --wait-max) WAIT_MAX="$2"; shift ;;
    --force) FORCE=1 ;;
    --no-build) BUILD=0 ;;
    --no-external) EXTERNAL=0 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
  shift
done

log() { printf '[deploy] %s\n' "$*"; }
fail() { printf '[deploy] 중단: %s\n' "$*" >&2; exit 1; }

# ── 1. main 최신 확인 ─────────────────────────────────────
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || fail "main 이 아닙니다 (현재 $BRANCH). git checkout main 뒤 다시."
[ -z "$(git status --porcelain --untracked-files=no)" ] || fail "추적 파일에 변경이 있습니다. 커밋하거나 되돌린 뒤 다시."
git fetch -q origin main
HEAD_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"
[ "$HEAD_SHA" = "$REMOTE_SHA" ] || fail "main 이 origin/main 과 다릅니다 (local ${HEAD_SHA:0:7}, origin ${REMOTE_SHA:0:7}). git pull 뒤 다시."
SHORT="${HEAD_SHA:0:7}"
PREV_SHA="$("$PY" - "$VERSION_FILE" <<'EOF'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("commit", ""))
except Exception:
    print("")
EOF
)"
PREV_SHORT="${PREV_SHA:0:7}"
log "main $SHORT (지난 배포: ${PREV_SHORT:-없음})"
if [ -n "$PREV_SHA" ] && [ "$PREV_SHA" = "$HEAD_SHA" ]; then
  log "지난 배포와 같은 커밋입니다 — 재시작만 합니다."
fi

# 반영 PR 목록: 지난 배포 이후 병합 커밋 제목의 #번호 + pending.md
PRS=""
if [ -n "$PREV_SHA" ] && git cat-file -e "$PREV_SHA" 2>/dev/null; then
  PRS="$(git log --merges --format=%s "$PREV_SHA..HEAD" | grep -oE '#[0-9]+' | sort -u | tr '\n' ' ')"
fi
PENDING_LINES=""
if [ -f "$PENDING" ]; then
  PENDING_LINES="$(grep -E '^- ' "$PENDING" || true)"
fi

# ── 2. web 빌드 ───────────────────────────────────────────
NEED_BUILD=0
if [ "$BUILD" = 1 ]; then
  if [ ! -f "$ROOT/web/dist/index.html" ]; then
    NEED_BUILD=1; log "web/dist 가 없어 빌드합니다."
  elif [ -z "$PREV_SHA" ] || ! git cat-file -e "$PREV_SHA" 2>/dev/null; then
    NEED_BUILD=1; log "지난 배포 커밋을 알 수 없어 web 을 빌드합니다."
  elif [ -n "$(git diff --name-only "$PREV_SHA" HEAD -- web/ docs/openapi.json)" ]; then
    NEED_BUILD=1; log "web/ 이 바뀌어 빌드합니다."
  else
    log "web/ 변경 없음 — 빌드 생략."
  fi
fi
if [ "$NEED_BUILD" = 1 ] && [ "$DRY" = 0 ]; then
  [ -d "$ROOT/web/node_modules" ] || (cd "$ROOT/web" && npm ci --no-audit --no-fund)
  (cd "$ROOT/web" && npm run build) || fail "npm run build 실패"
fi

# ── 3. 대기·실행 중인 생성 run ────────────────────────────
active_count() { "$RRA" runs active --json 2>/dev/null | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["count"])' 2>/dev/null || echo "?"; }
ACTIVE="$(active_count)"
WAITED=0
if [ "$ACTIVE" = "?" ]; then
  [ "$FORCE" = 1 ] || fail "run 상태를 읽지 못했습니다 (rra runs active). --force 로 무시할 수 있습니다."
  log "경고: run 상태를 읽지 못했지만 --force 로 진행합니다."
elif [ "$ACTIVE" != "0" ]; then
  if [ "$WAIT" = 1 ]; then
    log "대기·실행 중인 생성 ${ACTIVE}건 — 끝날 때까지 기다립니다 (최대 ${WAIT_MAX}초)."
    while [ "$ACTIVE" != "0" ] && [ "$WAITED" -lt "$WAIT_MAX" ]; do
      sleep 20; WAITED=$((WAITED + 20)); ACTIVE="$(active_count)"
    done
    [ "$ACTIVE" = "0" ] || fail "${WAIT_MAX}초가 지나도 생성 ${ACTIVE}건이 남아 있습니다. --force 또는 나중에 다시."
    log "생성이 모두 끝났습니다 (${WAITED}초 대기)."
  elif [ "$FORCE" = 1 ]; then
    log "경고: 대기·실행 중인 생성 ${ACTIVE}건이 있지만 --force 로 재시작합니다 (그 run 은 interrupted 가 됩니다)."
  else
    fail "대기·실행 중인 생성이 ${ACTIVE}건 있습니다. 끝날 때까지 기다리려면 --wait, 무시하려면 --force."
  fi
else
  log "대기·실행 중인 생성 0건."
fi

if [ "$DRY" = 1 ]; then
  log "--dry-run: 여기까지 (빌드 필요: $NEED_BUILD, 반영 PR: ${PRS:-없음}). 재시작·기록 없음."
  exit 0
fi

# ── 4. 버전 기록 → 재시작 ─────────────────────────────────
STAMP="$(date +%Y-%m-%dT%H:%M:%S%z)"
mkdir -p "$DATA_DIR/deploy"
"$PY" - "$VERSION_FILE" "$HEAD_SHA" "$STAMP" "$PRS" <<'EOF'
import json, os, sys
path, commit, stamp, prs = sys.argv[1:5]
data = {"commit": commit, "short": commit[:7], "deployed_at": stamp, "prs": prs.split()}
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
os.replace(tmp, path)
EOF
log "version.json 기록 ($SHORT, $STAMP)."
launchctl kickstart -k "gui/$(id -u)/$LABEL" || fail "launchctl kickstart 실패 — launchctl list | grep $LABEL 확인."
log "$LABEL 재시작."

# ── 5. 확인 ───────────────────────────────────────────────
check_health() {  # $1 = base url, $2 = timeout sec → 배포된 commit 을 출력(실패면 빈 문자열)
  curl -s -m "$2" "$1/healthz" 2>/dev/null | "$PY" -c 'import json,sys
try:
    d = json.load(sys.stdin); print(d.get("version", {}).get("commit", "") if d.get("status") == "ok" else "")
except Exception:
    print("")' 2>/dev/null || echo ""
}
GOT=""; TRIES=0
while [ "$TRIES" -lt 30 ]; do
  GOT="$(check_health "$LOCAL_URL" 3)"
  [ "$GOT" = "$HEAD_SHA" ] && break
  sleep 2; TRIES=$((TRIES + 1))
done
HEALTH_OK=0; LOGIN_OK=0; EXT_OK="생략"
if [ "$GOT" = "$HEAD_SHA" ]; then HEALTH_OK=1; log "healthz ok — 버전 $SHORT."; else log "경고: healthz 가 $SHORT 를 보고하지 않습니다 (받은 값: ${GOT:0:7}). ~/Library/Logs/rra-api.err.log 확인."; fi
LOGIN_CODE="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$LOCAL_URL/login" || echo 000)"
if [ "$LOGIN_CODE" = "200" ]; then LOGIN_OK=1; log "로그인 화면 200."; else log "경고: /login 이 $LOGIN_CODE 입니다 (web/dist 확인)."; fi
if [ "$EXTERNAL" = 1 ]; then
  EXT_GOT="$(check_health "$EXTERNAL_URL" 10)"
  if [ "$EXT_GOT" = "$HEAD_SHA" ]; then EXT_OK="ok"; log "외부 주소 $EXTERNAL_URL ok."; else EXT_OK="실패"; log "경고: 외부 주소 $EXTERNAL_URL 확인 실패 (Tailscale/Funnel 상태 확인)."; fi
fi
FUNNEL_OK="생략"
if [ "$EXTERNAL" = 1 ]; then  # 읽기 전용 — funnel/serve 설정을 바꾸는 명령은 이 스크립트에 없다
  if [ -x "$TAILSCALE" ] && "$TAILSCALE" funnel status 2>/dev/null | grep -q "(Funnel on)"; then
    FUNNEL_OK="on"; log "Tailscale Funnel on."
  else
    FUNNEL_OK="꺼짐"
    log "경고: Tailscale Funnel 이 꺼져 있습니다 — 외부에서 접속할 수 없습니다. 운영자가 직접:"
    log "  $TAILSCALE funnel --bg --https=443 http://127.0.0.1:8000"
  fi
fi

# ── 6. 기록 ───────────────────────────────────────────────
mkdir -p "$DEPLOY_DIR"
RECORD="$DEPLOY_DIR/$(date +%Y-%m-%d-%H%M).md"
{
  echo "# 배포 $STAMP — $SHORT"
  echo
  echo "| 항목 | 값 |"
  echo "|---|---|"
  echo "| 커밋 | \`$HEAD_SHA\` (이전 \`${PREV_SHA:-없음}\`) |"
  echo "| 반영 PR | ${PRS:-없음} |"
  echo "| web 빌드 | $([ "$NEED_BUILD" = 1 ] && echo 실행 || echo 생략) |"
  echo "| 생성 run 대기 | ${WAITED}초 (force=$FORCE) |"
  echo "| healthz | $([ "$HEALTH_OK" = 1 ] && echo ok || echo 실패) |"
  echo "| 로그인 화면 | $([ "$LOGIN_OK" = 1 ] && echo ok || echo "실패($LOGIN_CODE)") |"
  echo "| 외부 주소 | $EXT_OK ($EXTERNAL_URL, 이 맥에서는 tailnet 경로) |"
  echo "| Funnel on | $FUNNEL_OK |"
  if [ -n "$PENDING_LINES" ]; then
    echo
    echo "## 반영 대기 목록(pending.md)에서 옮김"
    echo
    echo "$PENDING_LINES"
  fi
} > "$RECORD"
if [ -f "$PENDING" ]; then
  "$PY" - "$PENDING" <<'EOF'
import sys
path = sys.argv[1]
lines = open(path, encoding="utf-8").read().splitlines()
kept = [l for l in lines if not l.startswith("- ")]
open(path, "w", encoding="utf-8").write("\n".join(kept).rstrip("\n") + "\n")
EOF
fi
log "기록: ${RECORD#$ROOT/} (pending.md 비움). 이 파일은 docs PR 로 커밋한다."
[ "$HEALTH_OK" = 1 ] && [ "$LOGIN_OK" = 1 ] && [ "$FUNNEL_OK" != "꺼짐" ] || exit 1
