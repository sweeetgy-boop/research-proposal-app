import { useSyncExternalStore } from "react";
import { isLoggedIn, subscribeSession } from "./session";

export function useLoggedIn(): boolean {
  return useSyncExternalStore(subscribeSession, isLoggedIn, isLoggedIn);
}
