import type { VersionRowMeta } from "@/api/types";

/** 목록 줄 — 내용 버전 한 줄, 또는 예전 run 의 상태만 바뀐 버전들을 접은 "확인 기록" 한 줄 (항목 21) */
export type Row = { kind: "version"; v: VersionRowMeta } | { kind: "fold"; rows: VersionRowMeta[] };

export function foldVersions(versions: VersionRowMeta[]): Row[] {
  const out: Row[] = [];
  for (const v of versions) {
    const last = out[out.length - 1];
    if (v.status_only) {
      if (last && last.kind === "fold") last.rows.push(v);
      else out.push({ kind: "fold", rows: [v] });
    } else out.push({ kind: "version", v });
  }
  return out;
}
