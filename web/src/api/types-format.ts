/** 레인 D(항목 2·16·17) 응답 모양 — entrypoints/api/routes_format.py · views.py 를 따라 손으로 적는다. */
import type { ProposalRequest, RunStatus, VersionOut } from "./types";

/** GET /v1/runs/{id}/request — 단계 표시 ①·② 를 run 안에서 열 때 */
export interface RunInputsOut {
  run_id: string;
  request: ProposalRequest;
  priority_evidence: string[];
  draft_version: number;
  status: RunStatus;
}

export interface RequestChangeIn {
  request: ProposalRequest;
  /** null·생략이면 우선 근거는 비교하지 않는다 */
  priority_evidence?: string[] | null;
}

export type RegenerateMode = "sections" | "all";

export interface RegenerateIn extends RequestChangeIn {
  mode: RegenerateMode;
  base_version?: number | null;
}

export interface ChangedField {
  field: string;
  label: string;
}

export interface SectionRef {
  key: string;
  title: string;
}

/** POST /v1/runs/{id}/request/preview — 저장하지 않는다 */
export interface RequestPreviewOut {
  run_id: string;
  fields: ChangedField[];
  sections: SectionRef[];
  all_sections: number;
  can_regenerate: boolean;
  reason: string | null;
  version: number;
}

/** POST /v1/runs/{id}/regenerate */
export interface RegenerateOut extends VersionOut {
  run_id: string;
  status: RunStatus;
  mode: RegenerateMode;
  fields: ChangedField[];
  regenerated: SectionRef[];
  failed: (SectionRef & { reason_label: string })[];
  kept: SectionRef[];
  saved_only: boolean;
}

/** 제출 전 점검 — 선택형 확정 줄 (choices_confirmed.choices) */
export interface CheckChoiceRow {
  key: string;
  title: string;
  confirmed: string[];
  proposed: string[];
  options: { id: string; label: string }[];
  min: number;
  max: number;
}

/** 제출 전 점검 — 미해결 알림 설명 줄 (unresolved_alerts.by_label) */
export interface CheckAlertRow {
  code: string;
  label: string;
  count: number;
  severity: string;
  severity_label: string;
}

/** 사용 기록 화면 줄 (usage.steps) — sections 는 벽시계, sections_sum 은 보조 */
export interface UsageStepRow {
  key: string;
  label: string;
  seconds: number;
  secondary: boolean;
}
