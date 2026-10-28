/** [G] 그림 v2 (2026-10-28, 레인 C) — As-Is/To-Be·분석 기법 추천의 손으로 쓴 타입.
 *  docs/openapi.json 이 다시 만들어지기 전까지 이 파일이 새 필드를 정의한다 (types.ts 가 다시 내보낸다). */
import type {
  Figure,
  FigureKind,
  FiguresOut,
  VersionWithStatus,
} from "./types";

export type FigureKindV2 = FigureKind | "as_is_to_be" | "technique";

/** 추천 결정 — pending(결정 전) | accepted(넣기 확정) | dismissed(필요 없음) */
export type RecommendationStatus = "pending" | "accepted" | "dismissed";

/** 추천 배지. reason 은 LLM 출력(비신뢰) — UntrustedText 로 보여 준다 */
export interface FigureRecommendation {
  technique: string;
  technique_label: string;
  reason: string;
  status: RecommendationStatus;
  status_label: string;
  swapped_from: string | null;
  swapped_from_label: string | null;
  model: string | null;
}

/** 기법 항목 출처 — 본문 문장(section·sentence_no)·제안 입력·근거 자료 */
export interface FigureProvenanceRow {
  group: string;
  text: string;
  rating: string;
  amount: string;
  source_kind: "sentence" | "input" | "evidence";
  section: string | null;
  sentence_no: number | null;
  source_label: string;
}

/** [23] 본문 폭 맞춤 — 카드는 그림을 aspect_css 비율로 보이고 note 한 줄을 붙인다 */
export interface FigureFitView {
  /** 고른 비율 "16:9" | "21:9" | "4:1" */
  ratio: string;
  /** CSS aspect-ratio 값 "21 / 9" */
  aspect_css: string;
  width_mm: number;
  height_mm: number;
  /** 높이 ≤ 쪽 높이 1/3 */
  fits: boolean;
  min_text_pt: number | null;
  text_ok: boolean;
  shortened: number;
  /** "본문 폭 153.8mm × 높이 65.9mm · 가장 작은 글자 약 9.3pt" */
  note: string;
}

/** 그림 v2 필드 — 기법 그림이 아니면 technique 등은 null, provenance 는 빈 목록 */
export interface FigureV2Fields {
  /** [23] 화면·버전 목록 이름 (한국어) — "현재·연구 후 비교 그림", "분석 기법 그림 – SWOT 분석" */
  display_name: string;
  /** [23] 오류 코드 대신 보이는 한국어 한 줄 (오류 없으면 null) */
  error_label: string | null;
  /** [23] 본문 폭 맞춤 (옛 그림은 null) */
  fit: FigureFitView | null;
  technique: string | null;
  family_label: string | null;
  prelim_note: string | null;
  provenance: FigureProvenanceRow[];
  recommendation: FigureRecommendation | null;
}

export type FigureV2 = Omit<Figure, "kind"> & {
  kind: FigureKindV2 | string;
} & Partial<FigureV2Fields>;

/** 마지막 분석 기법 추천 결과 — 빈 결과도 사유(해당 없음·호출 실패·규칙에 걸러짐·건너뜀) */
export interface TechniqueOutcome {
  status: "recommended" | "none" | "failed" | "filtered" | "off";
  status_label: string;
  message: string;
  picks: { key: string; label: string }[];
  dropped: { key: string; label: string }[];
  model: string | null;
  at: string | null;
  can_retry: boolean;
}

/** 기법 목록 한 줄 ([다른 기법으로 바꾸기]·[다른 그림 추가]) */
export interface TechniqueCatalogRow {
  key: string;
  label: string;
  family: string;
  family_label: string;
  section: string;
  summary: string;
  fits: string;
}

/** GET /v1/runs/{id}/figures — v2 */
export interface FiguresOutV2 extends Omit<FiguresOut, "figures"> {
  figures: FigureV2[];
  techniques: TechniqueOutcome | null;
  technique_catalog: TechniqueCatalogRow[];
}

export type FigureActionV2 =
  | "words"
  | "texts"
  | "baseline"
  | "regenerate"
  | "include"
  | "exclude"
  | "confirm"
  | "accept"
  | "dismiss"
  | "restore"
  | "swap";

/** POST /v1/runs/{id}/figures/{fid} — v2 (swap 은 technique 필수) */
export interface FigureActionV2In {
  action: FigureActionV2;
  request?: string;
  texts?: Record<string, string>;
  base_version?: number | null;
  technique?: string;
}

/** POST /v1/runs/{id}/figures — v2 (kind=technique 면 technique 필수) */
export interface FigureAddV2In {
  kind: FigureKindV2;
  section: string;
  base_version?: number | null;
  technique?: string;
}

/** POST /v1/runs/{id}/figures/techniques — [다시 추천] */
export interface FigureTechniquesIn {
  base_version?: number | null;
}

/** [다시 추천] 응답 — created 면 새 버전 필드가 함께 온다 */
export type FigureTechniquesOut = Partial<VersionWithStatus> & {
  run_id: string;
  status: string;
  created: boolean;
  techniques: TechniqueOutcome | null;
};
