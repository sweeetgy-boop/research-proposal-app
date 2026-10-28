/** 레인 D 경로 — run 입력 조회·변경 미리보기·다시 쓰기, 근거 일괄 승인, 내려받기 파일 이름. */
import { request } from "./client";
import type { RegenerateIn, RegenerateOut, RequestChangeIn, RequestPreviewOut, RunInputsOut, VersionWithStatus } from "./types";

const V = "/v1";
const enc = encodeURIComponent;

export const getRunInputs = (id: string) => request<RunInputsOut>(`${V}/runs/${enc(id)}/request`);
export const previewRequestChange = (id: string, body: RequestChangeIn) =>
  request<RequestPreviewOut>(`${V}/runs/${enc(id)}/request/preview`, { method: "POST", body });
export const regenerateRun = (id: string, body: RegenerateIn) =>
  request<RegenerateOut>(`${V}/runs/${enc(id)}/regenerate`, { method: "POST", body });
export const bulkApproveEvidence = (id: string, baseVersion?: number | null) =>
  request<VersionWithStatus>(`${V}/runs/${enc(id)}/evidence-decisions/bulk-approve`, {
    method: "POST",
    body: { base_version: baseVersion ?? null },
  });

/** Content-Disposition → 파일 이름. RFC 5987 filename*(UTF-8, 한글 제목)을 먼저, 없으면 ASCII filename. */
export function filenameFromDisposition(cd: string | null | undefined, fallback: string): string {
  const header = cd ?? "";
  const star = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(header);
  if (star?.[1]) {
    try {
      const decoded = decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
      if (decoded) return decoded;
    } catch {
      /* 잘못된 인코딩 — ASCII 이름으로 */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/.exec(header);
  return plain?.[1] ?? fallback;
}
