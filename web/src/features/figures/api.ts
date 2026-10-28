/** [G] 그림 v2 호출·훅 — 그림 목록(기법 추천 결과·기법 목록), 추천 카드 동작, [다시 추천], 기법 추가.
 *  모두 run 쿼리(keys.run)를 무효화해 초안·버전·목록이 함께 새로 고쳐진다. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/api/client";
import { keys } from "@/api/hooks";
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
) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/figures/${enc(fid)}`, {
    method: "POST",
    body,
  });
export const addFigureV2 = (id: string, body: FigureAddV2In) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/figures`, {
    method: "POST",
    body,
  });
export const retryTechniques = (id: string, body: FigureTechniquesIn) =>
  request<FigureTechniquesOut>(`${V}/runs/${enc(id)}/figures/techniques`, {
    method: "POST",
    body,
  });

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
