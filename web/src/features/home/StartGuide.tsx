/** "제안서 작성, 이렇게 시작하세요" — 우리 흐름(① 아이디어 입력 → ② 유사과제 확인 → ③~⑥ 초안·검토·마무리) 세 카드. */
import { Link } from "react-router";

const STEPS = [
  { n: "01", title: "아이디어 입력", text: "현재 상황·원인·한계·목표를 적거나 간편 입력으로 시작합니다." },
  { n: "02", title: "유사과제 확인", text: "기존 과제와 겹치는지 보고 차별화 방향을 고릅니다." },
  { n: "03", title: "초안·검토·마무리", text: "근거가 붙은 초안을 고치고, 최종 검토 뒤 양식 파일로 받습니다." },
];

export function StartGuide() {
  return (
    <section aria-labelledby="start-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="start-title" className="text-lg font-bold">
          제안서 작성, 이렇게 시작하세요
        </h2>
        <Link to="/guide" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
          작성 가이드 전체 보기
        </Link>
      </div>
      <ol className="mt-3 grid gap-3 md:grid-cols-3">
        {STEPS.map((s) => (
          <li key={s.n} className="flex items-start gap-3 rounded-xl border bg-card shadow-card p-4">
            <span
              aria-hidden="true"
              className="grid h-8 min-w-8 shrink-0 place-items-center rounded-lg bg-primary-soft px-1.5 text-sm font-semibold tabular-nums text-primary-soft-foreground"
            >
              {s.n}
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">{s.title}</span>
              <span className="mt-0.5 block text-sm text-muted-foreground">{s.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
