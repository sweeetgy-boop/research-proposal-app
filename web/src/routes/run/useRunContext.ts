import { useOutletContext } from "react-router";
import type { RunContext } from "./RunLayout";

export function useRunContext(): RunContext {
  return useOutletContext<RunContext>();
}
