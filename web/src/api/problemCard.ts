/** 문제 정의 카드 (ADR 0065, docs/contracts/problem-card.md 3절) — ① 화면이 뒤에서 부르는 진단과 줄 수정.
 *  카드는 화면 상태(IdeaState.problemCard)이고 서버는 세션에 두지 않는다. 응답 모양은 types-problem-card.ts.
 *  두 경로 모두 실패해도 화면은 카드 없이 그대로 간다 — 오류를 삼키는 일은 부르는 쪽(useProblemDiagnosis)이 한다. */
import { request } from "./client";
import type { CardEditIn, CardEditOut, DiagnoseIn, DiagnoseOut } from "./types-problem-card";

export const DIAGNOSE_PATH = "/v1/ideas/diagnose";
export const DIAGNOSE_EDIT_PATH = "/v1/ideas/diagnose/edit";

/** 네 칸(+가제)을 AI 1회로 진단. signal 로 끊으면 서버도 그 작업을 멈춘다. status 가 off·failed 면 card 는 null */
export const diagnoseProblem = (body: DiagnoseIn, opts: { signal?: AbortSignal } = {}) =>
  request<DiagnoseOut>(DIAGNOSE_PATH, { method: "POST", body, signal: opts.signal });

/** 한 줄 고치기 — fields 에 고친 항목. 서버가 그 항목을 제안자 수정으로 표시하고 기대는 것만 다시 계산한다 */
export const editProblemCard = (body: CardEditIn, opts: { signal?: AbortSignal } = {}) =>
  request<CardEditOut>(DIAGNOSE_EDIT_PATH, { method: "POST", body, signal: opts.signal });
