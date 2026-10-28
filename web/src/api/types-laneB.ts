/** 레인 B (2026-10-28 밤, ADR 0040) — L2 로컬 2차 검토·문서 표시 응답 모양. entrypoints/views.py·local_review_routes.py 를 따른다. */

export type LocalVerdict = "지지" | "부분" | "불일치";
export type LocalSuggestionStatus = "open" | "applied" | "dismissed" | "failed";

/** 불일치 문장에 Argon 이 낸 "근거 안에서 다시 쓰기 또는 빼기" 제안 — 자동 반영 없음 */
export interface LocalSuggestion {
  id: string;
  section: string;
  status: LocalSuggestionStatus;
  status_label: string;
  action: "rewrite" | "remove" | null;
  action_label: string | null;
  /** 다시 쓴 문장 (빼기면 빈 문자열) — LLM 출력(비신뢰) */
  text: string;
  reason: string;
  /** 실패·걸러짐 사유 (한국어) */
  reason_label?: string | null;
  /** 다시 쓴 문장이 근거 범위 검사에 걸려 "빼기"로 바뀌었다 */
  filtered: boolean;
  model?: string | null;
  fallback?: boolean;
  /** [반영] 으로 만든 버전 */
  version?: number | null;
  decided_at?: string | null;
}

/** 초안·편집 화면의 local_check (판정이 돈 run 만) */
export interface LocalReviewView {
  enabled: boolean;
  mismatches: number;
  skipped_sections: string[];
  /** 문장 id(s:<섹션>:<n>) → 판정 — 화면은 "로컬 검토: 지지/부분/불일치" */
  verdicts?: Record<string, LocalVerdict>;
  /** 문장 id → 제안 (지금 본문에 있는 문장만) */
  suggestions?: Record<string, LocalSuggestion>;
  /** 반영한 제안 기록 */
  applied?: LocalSuggestion[];
  /** 결정하지 않은 불일치 문장 수 */
  unresolved?: number;
  counts?: Partial<Record<LocalVerdict, number>>;
  seconds?: number | null;
}

export interface LocalReviewOut {
  run_id: string;
  notice?: string;
  local_check: LocalReviewView | null;
}

/** 문서 표시 정보 (citations·evidence_refs) — 화면은 doc_id 를 보이지 않는다 */
export interface DocRefOut {
  id?: string;
  doc_id: string;
  title: string;
  source: string;
  source_label: string;
  url: string | null;
  live?: boolean;
}
