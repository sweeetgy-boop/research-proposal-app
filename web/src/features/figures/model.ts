/** [G] 그림 카드 — 종류·변경 라벨, 기본 섹션, 이미지 주소 보조. 컴포넌트 없음(순수). */
import type { FigureKindV2 } from "@/api/types";

/** v2: As-Is/To-Be·분석 기법을 앞에 — 기본 그림(자동)은 As-Is/To-Be·수치 그래프·일정표·기법 추천 */
export const KIND_LABELS: Record<FigureKindV2, string> = {
  as_is_to_be: "현재·연구 후 비교 그림",
  technique: "분석 기법 그림",
  concept: "연구 개념도",
  process: "추진 체계도",
  schedule: "추진 일정표",
  stat_chart: "현황 수치 그래프",
  comparison: "차별성 비교표",
  roadmap: "성과지표·활용 로드맵",
};

export const FIGURE_KINDS = Object.keys(KIND_LABELS) as FigureKindV2[];

export const kindLabel = (kind: string): string => (KIND_LABELS as Record<string, string>)[kind] ?? kind;

/** [다른 그림 추가] 의 기본 섹션 */
export const KIND_SECTION: Record<FigureKindV2, string> = {
  as_is_to_be: "objective",
  technique: "method",
  concept: "objective",
  process: "method",
  schedule: "method",
  stat_chart: "tech_importance",
  comparison: "tech_importance",
  roadmap: "expected_technology",
};

/** 버전 비교 figures_changed.change → 한국어 */
export const CHANGE_LABELS: Record<string, string> = {
  added: "추가",
  removed: "삭제",
  redrawn: "다시 그림",
  texts: "글자 수정",
  included: "넣음",
  excluded: "뺌",
  confirmed: "확인함",
  baseline: "기본 그림으로",
  accepted: "추천 넣기 확정",
  dismissed: "추천 필요 없음",
  restored: "추천 다시 넣음",
  swapped: "다른 기법으로 바꿈",
};

export const changeLabel = (change: string): string => CHANGE_LABELS[change] ?? change;

/** 이미지 주소에 버전·캐시 무효화 값을 붙인다. baseline_url 은 이미 `?variant=baseline` 을 가진다. */
export function imageSrc(url: string, opts: { version?: number | null; v?: string | null } = {}): string {
  const params: string[] = [];
  if (opts.version !== undefined && opts.version !== null) params.push(`version=${encodeURIComponent(String(opts.version))}`);
  if (opts.v) params.push(`v=${encodeURIComponent(opts.v)}`);
  if (params.length === 0) return url;
  return `${url}${url.includes("?") ? "&" : "?"}${params.join("&")}`;
}

/** [23] 카드 제목 — API display_name(한국어), 없으면 종류 이름. 내부 id·영문 코드는 보이지 않는다 */
export function figureName(f: { display_name?: string | null; kind: string; label?: string }): string {
  if (f.display_name) return f.display_name;
  if (f.kind === "technique" && f.label) return `${kindLabel(f.kind)} – ${f.label}`;
  return kindLabel(f.kind);
}

/** [23] 그림 비율 (CSS aspect-ratio) — 맞춤 기록이 없으면 16 / 9 */
export function figureAspect(f: { fit?: { aspect_css?: string } | null }): string {
  return f.fit?.aspect_css || "16 / 9";
}
