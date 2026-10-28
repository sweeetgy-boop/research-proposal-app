/** 레인 D(항목 21) 버전 목록·변경 세기의 새 필드 — views.versions_payload · change_count.dump 를 따라 손으로 적는다. */
import type { ChangeItem, ChangesOut, VersionMeta } from "./types";

/** GET /v1/runs/{id}/versions 의 행에 붙는 설명 (ADR 0042) */
export interface VersionHistoryFields {
  /** 예전 run 의 상태만 바뀐 버전(그림 확인 등) — 화면이 "확인 기록" 으로 접는다 */
  status_only?: boolean;
  /** 바뀐 그림 — "연구 개념도 다시 그림" (이름, 내부 번호 없음) */
  changed_figures?: string[];
  /** 그 버전에 쌓인 확인 기록 문구 — "그림 확인 — 분석 기법 그림 – SWOT 분석" */
  marks?: string[];
  confirmations?: number;
  /** 메모를 한국어로 고친 설명 ("그림 confirm" → "그림 확인 — …") */
  description?: string;
}

export type VersionRowMeta = VersionMeta & VersionHistoryFields;

/** GET /v1/runs/{id}/changes — 변경(내용)과 확인(상태 표시)을 따로 */
export interface ChangesOutV2 extends ChangesOut {
  confirmations?: number;
  confirm_items?: ChangeItem[];
}
