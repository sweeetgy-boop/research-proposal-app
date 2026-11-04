import { TriangleAlert } from "lucide-react";
import { useArgonStatus } from "@/api/hooks";
import { useIsAdmin, useLoggedIn } from "@/auth/useSession";
import { ARGON_DOWN_TITLE, argonDownReason } from "@/lib/labels";

/** Argon(Gemini) 연결 오류 알림 띠 (ADR 0055) — 로그인한 모든 화면 맨 위. /healthz `llm.gemini` 가
 *  ok·unknown 이 아니면 보인다. 사유 줄(API 키 확인 필요·사용 한도 초과·응답 없음)은 관리자에게만.
 *  2026-10-30 ~ 11-03 Argon 키가 무효였던 나흘 동안 화면이 로컬 모델로 조용히 대체돼 아무도 몰랐던 일 뒤에 더했다.
 *  로그인 전에는 그리지 않는다(상태도 묻지 않는다). */
export function ArgonStatusBanner() {
  const loggedIn = useLoggedIn();
  const admin = useIsAdmin();
  const { data } = useArgonStatus(loggedIn);
  const reason = loggedIn ? argonDownReason(data?.gemini) : null;
  if (!reason) return null;
  return (
    <div
      role="status"
      data-testid="argon-status-banner"
      className="flex items-start gap-2 border-b border-warning/30 bg-apricot px-4 py-2 text-sm text-apricot-foreground"
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-semibold">{ARGON_DOWN_TITLE}</p>
        {admin && <p data-testid="argon-status-reason">{reason}</p>}
      </div>
    </div>
  );
}
