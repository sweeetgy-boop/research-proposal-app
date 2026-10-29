/** 위쪽 경로 표시 — 주소 → "Research Studio › 연구 작업실 › …". 순수 함수(제안서 제목은 밖에서 넣는다). */
import { stepLabel, runStepFromSub } from "@/lib/runSteps";

export const APP_NAME = "Research Studio";

export interface Crumb {
  label: string;
  /** 누르면 갈 곳. 없으면 지금 화면(마지막 칸) */
  to?: string;
}

const RUN_SUB: Record<string, string> = {
  "": "진행",
  idea: "아이디어",
  precheck: "유사과제",
  draft: "초안 보기",
  edit: "직접 수정",
  versions: "버전·비교",
  "final-review": "최종 검토",
  "submit-check": "제출 전 점검",
  finalize: "최종 마무리",
};

const NEW_SUB: Record<string, { label: string; step: number }> = {
  "/new": { label: "아이디어 입력", step: 1 },
  "/new/precheck": { label: "유사과제 확인", step: 2 },
  "/new/brief": { label: "선행연구 브리핑", step: 2 },
  "/new/clarify": { label: "보강 질문", step: 3 },
};

const PAGES: Record<string, string> = {
  "/runs": "내 제안서",
  "/guide": "작성 가이드",
  "/search": "자료 검색",
  "/sources": "자료 현황",
};

const circled = (n: number) => "①②③④⑤⑥"[n - 1] ?? "";

/** 경로 → 칸 목록. 첫 칸은 앱 이름, 둘째 칸은 연구 작업실(홈). runTitle 은 제안서 안에서만 쓴다. */
export function crumbsFor(pathname: string, runTitle?: string | null): Crumb[] {
  const base: Crumb[] = [{ label: APP_NAME, to: "/" }, { label: "연구 작업실", to: "/" }];
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return [base[0]!, { label: "연구 작업실" }];
  const n = NEW_SUB[path];
  if (n) return [...base, { label: "새 제안서", to: "/new" }, { label: `${circled(n.step)} ${n.label}` }];
  const page = PAGES[path];
  if (page) return [...base, { label: page }];
  const m = /^\/runs\/([^/]+)(?:\/([a-z-]+))?$/.exec(path);
  if (m) {
    const sub = m[2] ?? "";
    const title = (runTitle ?? "").trim() || "제목 미정";
    const step = runStepFromSub(sub || undefined);
    const subLabel = RUN_SUB[sub] ?? stepLabel(step ?? 0);
    const last = step ? `${circled(step)} ${subLabel}` : subLabel;
    return [...base, { label: "내 제안서", to: "/runs" }, { label: title, to: `/runs/${m[1]}` }, { label: last }];
  }
  return base.slice(0, 2).map((c, i) => (i === 1 ? { label: c.label } : c));
}
