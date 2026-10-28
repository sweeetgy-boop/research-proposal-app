/** [G] 그림 카드 — 종류·변경 라벨, 기본 섹션, 이미지 주소 보조. 컴포넌트 없음(순수). */
import type { FigureKind } from "@/api/types";

export const KIND_LABELS: Record<FigureKind, string> = {
  concept: "연구 개념도",
  process: "추진 체계도",
  schedule: "추진 일정표",
  stat_chart: "현황 수치 그래프",
  comparison: "차별성 비교",
  roadmap: "성과지표·활용 로드맵",
};

export const FIGURE_KINDS = Object.keys(KIND_LABELS) as FigureKind[];

export const kindLabel = (kind: string): string => (KIND_LABELS as Record<string, string>)[kind] ?? kind;

/** [다른 그림 추가] 의 기본 섹션 */
export const KIND_SECTION: Record<FigureKind, string> = {
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
