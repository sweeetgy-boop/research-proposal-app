/** [4] 실시간 검색 — 자료원·상태 라벨 (화면 문구는 여기 한 곳) */
import type { BadgeProps } from "@/components/ui/badge";

export const LIVE_SOURCE_LABELS: Record<string, string> = {
  scienceon: "ScienceON",
  ntis: "NTIS",
  openalex: "OpenAlex",
};

export const LIVE_SOURCE_STATUS_LABELS: Record<string, string> = {
  ok: "완료",
  timeout: "시간 초과",
  ip_blocked: "IP 차단",
  error: "오류",
  off: "꺼짐",
};

export const LIVE_SEARCH_STATUS_LABELS: Record<string, string> = {
  done: "완료",
  partial: "일부 완료",
  pending: "검색 중",
  off: "꺼짐",
};

type Variant = NonNullable<BadgeProps["variant"]>;

export const LIVE_SOURCE_STATUS_VARIANT: Record<string, Variant> = {
  ok: "success",
  timeout: "warning",
  ip_blocked: "destructive",
  error: "destructive",
  off: "outline",
};

export const LIVE_SEARCH_STATUS_VARIANT: Record<string, Variant> = {
  done: "success",
  partial: "warning",
  pending: "info",
  off: "outline",
};

export const liveSourceLabel = (s: string): string => LIVE_SOURCE_LABELS[s] ?? s;
export const liveSourceStatusLabel = (s: string): string => LIVE_SOURCE_STATUS_LABELS[s] ?? s;
export const liveSearchStatusLabel = (s: string): string => LIVE_SEARCH_STATUS_LABELS[s] ?? s;
