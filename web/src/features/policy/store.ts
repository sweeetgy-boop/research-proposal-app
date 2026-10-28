/** ③ 보강 질문에서 고른 정책 근거 — 새로고침에 견디도록 sessionStorage (정책 자료 인용·제안자 글뿐, 개인정보 없음).
 *  아이디어 저장소(features/idea/store)와 따로 둔다 — 생성 요청 때 RunIn.policy_choice 로 보낸다. */
import { useSyncExternalStore } from "react";
import type { PolicyChoice } from "@/api/types";

const KEY = "rra-policy-choice";
const listeners = new Set<() => void>();

function load(): PolicyChoice | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as PolicyChoice) : null;
  } catch {
    return null;
  }
}

let current: PolicyChoice | null = load();

export function setPolicyChoice(choice: PolicyChoice | null): void {
  current = choice;
  try {
    if (choice) sessionStorage.setItem(KEY, JSON.stringify(choice));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  for (const l of listeners) l();
}

export function getPolicyChoice(): PolicyChoice | null {
  return current;
}

export function usePolicyChoice(): PolicyChoice | null {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => current,
    () => current,
  );
}
