/** 배포 시각 → "10-28 09:34" (화면 하단, 동료가 어떤 버전을 쓰는지 알 수 있게) */
export function formatDeployedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
