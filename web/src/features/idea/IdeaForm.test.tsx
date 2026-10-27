import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IdeaForm } from "./IdeaForm";
import { emptyRequest } from "@/lib/validation";
import { expectNoA11yViolations } from "@/test/utils";
import type { ProposalRequest } from "@/api/types";
import * as React from "react";

function Harness({ onSubmit }: { onSubmit: (r: ProposalRequest) => void }) {
  const [v, setV] = React.useState<ProposalRequest>(emptyRequest());
  return <IdeaForm value={v} onChange={(p) => setV((s) => ({ ...s, ...p }))} onSubmit={onSubmit} />;
}

describe("IdeaForm", () => {
  it("빈 채로 제출하면 필수 슬롯 메시지와 필드별 오류, onSubmit 호출 없음", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole("button", { name: "유사과제 확인" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("필수 슬롯이 비었습니다: 현재 상황·문제, 발생 원인, 현행 대응의 한계, 해결 목표");
    expect(screen.getByLabelText(/현재 상황·문제/)).toHaveAttribute("aria-invalid", "true");
  });

  it("필수 4개를 채우면 제출된다", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText(/현재 상황·문제/), "궤도 틀림 반복");
    await userEvent.type(screen.getByLabelText(/발생 원인/), "다짐 효과 짧음");
    await userEvent.type(screen.getByLabelText(/현행 대응의 한계/), "주기 보수 한계");
    await userEvent.type(screen.getByLabelText(/해결 목표/), "우선순위 산정");
    await userEvent.click(screen.getByRole("button", { name: "유사과제 확인" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ current_state: "궤도 틀림 반복", goal: "우선순위 산정" });
  });

  it("길이 상한을 넘으면 백엔드 문구와 같은 오류", async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const ta = screen.getByLabelText(/현재 상황·문제/);
    await userEvent.click(ta);
    await userEvent.paste("x".repeat(2001));
    await userEvent.click(screen.getByRole("button", { name: "유사과제 확인" }));
    expect(screen.getByText("슬롯 길이 2001 > 2000")).toBeInTheDocument();
  });

  it("접근성 위반 없음", async () => {
    const { container } = render(<Harness onSubmit={() => undefined} />);
    await expectNoA11yViolations(container);
  });
});
