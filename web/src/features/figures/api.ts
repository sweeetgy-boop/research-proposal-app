/** [G] 그림 v2 호출·훅 — 그림 목록(기법 추천 결과·기법 목록), 추천 카드 동작, [다시 추천], 기법 추가.
 *  모두 run 쿼리(keys.run)를 무효화해 초안·버전·목록이 함께 새로 고쳐진다. */
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/api/client";
import { keys } from "@/api/hooks";
import { useAiCall } from "@/lib/useAiCall";
import type {
  FigureActionV2In,
  FigureAddV2In,
  FiguresOutV2,
  FigureTechniquesIn,
  FigureTechniquesOut,
  VersionWithStatus,
} from "@/api/types";

const V = "/v1";
const enc = encodeURIComponent;

export const getFiguresV2 = (id: string) =>
  request<FiguresOutV2>(`${V}/runs/${enc(id)}/figures`);
export const figureActionV2 = (
  id: string,
  fid: string,
  body: FigureActionV2In,
  signal?: AbortSignal,
) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/figures/${enc(fid)}`, {
    method: "POST",
    body,
    signal,
  });
export const addFigureV2 = (id: string, body: FigureAddV2In, signal?: AbortSignal) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/figures`, {
    method: "POST",
    body,
    signal,
  });
export const retryTechniques = (id: string, body: FigureTechniquesIn, signal?: AbortSignal) =>
  request<FigureTechniquesOut>(`${V}/runs/${enc(id)}/figures/techniques`, {
    method: "POST",
    body,
    signal,
  });

/** [23] AI 를 부르는 그림 동작(다시 만들기·말로 고치기·기법 바꾸기·그림 추가·다시 추천) — 시간 제한 없이 기다리고
 *  경과 초와 [취소]. 취소하면 서버 작업도 멈추고(499) 화면은 이전 상태. 성공하면 run 쿼리를 무효화한다. */
function useInvalidatingAi<A, R>(id: string, fn: (args: A, signal: AbortSignal) => Promise<R>) {
  const qc = useQueryClient();
  const wrapped = React.useCallback(
    async (args: A, signal: AbortSignal) => {
      const out = await fn(args, signal);
      // 기다리지 않는다 — 다시 불러오는 동안 카드가 다시 그려져도(언마운트) 결과는 그대로 돌려준다
      void qc.invalidateQueries({ queryKey: keys.run(id) });
      return out;
    },
    [fn, id, qc],
  );
  return useAiCall(wrapped);
}

export function useFigureActionAi(id: string) {
  const fn = React.useCallback(
    ({ fid, body }: { fid: string; body: FigureActionV2In }, signal: AbortSignal) => figureActionV2(id, fid, body, signal),
    [id],
  );
  return useInvalidatingAi(id, fn);
}

export function useAddFigureAi(id: string) {
  const fn = React.useCallback((body: FigureAddV2In, signal: AbortSignal) => addFigureV2(id, body, signal), [id]);
  return useInvalidatingAi(id, fn);
}

export function useRetryTechniquesAi(id: string) {
  const fn = React.useCallback((body: FigureTechniquesIn, signal: AbortSignal) => retryTechniques(id, body, signal), [id]);
  return useInvalidatingAi(id, fn);
}

/** 그림 목록 + 기법 추천 결과 + 기법 목록 (keys.figures — run 무효화에 함께 걸린다) */
export function useFiguresV2(id: string, enabled = true) {
  return useQuery({
    queryKey: keys.figures(id),
    queryFn: () => getFiguresV2(id),
    enabled: enabled && !!id,
    staleTime: 10_000,
  });
}

export function useFigureActionV2(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ fid, body }: { fid: string; body: FigureActionV2In }) =>
      figureActionV2(id, fid, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useAddFigureV2(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FigureAddV2In) => addFigureV2(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useRetryTechniques(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FigureTechniquesIn) => retryTechniques(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}
