/** [3] Argon 우선 작성 — 작성자·실패 사유 라벨 */
import type { SectionWriter } from "@/api/types";

export const WRITER_REASON_LABELS: Record<string, string> = {
  error: "오류",
  rate_limit: "호출 한도",
  budget: "일일 상한",
  invalid: "형식 오류",
};

export const writerReasonLabel = (r: string | null | undefined): string | null => (r ? (WRITER_REASON_LABELS[r] ?? r) : null);

/** "로컬 작성" 배지 설명 — title 과 화면 낭독용 문구에 같이 쓴다 */
export function localWriterNote(writer: SectionWriter | undefined): string {
  const reason = writerReasonLabel(writer?.reason);
  return reason ? `Argon 작성 실패(${reason}) 뒤 로컬 모델이 작성` : "Argon 작성 실패 뒤 로컬 모델이 작성";
}

/** 근거 대조(로컬) 불일치 알림 코드 */
export const LOCAL_EVIDENCE_MISMATCH = "local_evidence_mismatch";
export const LOCAL_EVIDENCE_MISMATCH_LABEL = "근거 대조(로컬) 불일치";
