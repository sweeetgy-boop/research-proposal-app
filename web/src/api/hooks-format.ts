/** 레인 D 훅 — run 입력(①·②) 조회·변경 미리보기·다시 쓰기, 근거 일괄 승인, 선택형 확정. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./endpoints-format";
import { confirmChoices } from "./endpoints";
import { keys } from "./hooks";
import type { ConfirmIn, RegenerateIn, RequestChangeIn } from "./types";

export const formatKeys = {
  inputs: (id: string) => ["run", id, "inputs"] as const,
};

export function useRunInputs(id: string, enabled = true) {
  return useQuery({ queryKey: formatKeys.inputs(id), queryFn: () => api.getRunInputs(id), enabled });
}

export function usePreviewRequestChange(id: string) {
  return useMutation({ mutationFn: (body: RequestChangeIn) => api.previewRequestChange(id, body) });
}

/** 다시 쓰기 성공 → run 아래 전부(초안·버전·입력·점검) 무효화 */
export function useRegenerate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RegenerateIn) => api.regenerateRun(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useBulkApprove(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (baseVersion: number | null) => api.bulkApproveEvidence(id, baseVersion),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

export function useConfirmChoices(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ConfirmIn) => confirmChoices(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.run(id) }),
  });
}

/** 선택형 섹션 키 → ConfirmIn 칸 */
export function confirmBody(key: string, ids: string[]): ConfirmIn {
  if (key === "task_type") return { task_type: ids[0] ?? null };
  if (key === "utilization") return { utilization: ids };
  return { strategy: ids };
}
