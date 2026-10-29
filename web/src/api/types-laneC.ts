/** 레인 C (2026-10-29, ADR 0045) — 초안 글 먼저·그림은 백그라운드. docs/openapi.json 이 다시 만들어지기
 *  전까지 이 파일이 새 필드를 정의한다 (types.ts 가 다시 내보낸다). */
import type { RunState } from "./types";

/** 그림 작업 상태 — null 이면 그림 단계 없음·예전 제안서 */
export type FiguresStatus = "pending" | "drawing" | "done" | "failed";

/** 그림 카드 자리 — 그리는 중(drawing)·실패(failed)·걸러짐(skipped, 그림이 한 장도 없을 때만) */
export interface FigureSlot {
  slot_id: string;
  kind: string;
  /** 붙는 섹션. 분석 기법 추천 자리는 빈 값(섹션을 아직 모른다) */
  section: string;
  /** 화면 이름 (한국어) */
  display_name: string;
  status: "drawing" | "failed" | "skipped" | "done";
  /** 실패·걸러짐 사유 한 줄 (한국어, 코드 없음). 그리는 중이면 null */
  reason_label: string | null;
}

/** GET /v1/runs/{id} 에 붙는 그림 작업 필드 */
export interface FigureJobFields {
  figures_status: FiguresStatus | null;
  figure_slots: FigureSlot[];
  /** 제출 → 초안 글 보임 (초) */
  draft_visible_seconds: number | null;
  /** 제출 → 그림 모두 끝남 (초). 그리는 중이면 null */
  figures_done_seconds: number | null;
}

export type RunWithFigureJob = RunState & Partial<FigureJobFields>;

/** GET /v1/runs/{id}/sections-progress — 작성 중 섹션 먼저 보기 (버전 아님, 마무리 정리 전 글) */
export interface SectionsProgress {
  run_id: string;
  notice: string;
  status: RunState["status"];
  sections: { key: string; sentences: string[] }[];
  pending: string[];
}
