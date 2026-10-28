import { act, fireEvent, render, screen } from "@testing-library/react";
import { AiWaiting } from "@/components/AiWaiting";
import { useAiCall } from "./useAiCall";

function Harness({ fn }: { fn: (a: string, s: AbortSignal) => Promise<string> }) {
  const call = useAiCall(fn);
  return (
    <div>
      <button onClick={() => void call.run("x")}>시작</button>
      <AiWaiting pending={call.pending} elapsed={call.elapsed} onCancel={call.cancel} what="Argon" />
      <p data-testid="data">{call.data ?? "없음"}</p>
      <p data-testid="state">{call.cancelled ? "취소됨" : call.error ? "오류" : "정상"}</p>
    </div>
  );
}

describe("useAiCall", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("기다리는 동안 경과 초를 세고, 끝나면 결과를 남긴다 (시간 제한 없음)", async () => {
    let resolve!: (v: string) => void;
    render(<Harness fn={() => new Promise<string>((r) => (resolve = r))} />);
    fireEvent.click(screen.getByText("시작"));
    expect(screen.getByRole("status")).toHaveTextContent("Argon — 응답 기다리는 중 · 경과 0초");
    await act(async () => {
      vi.advanceTimersByTime(305_000); // 5분이 지나도 기다린다
    });
    expect(screen.getByRole("status")).toHaveTextContent("경과 305초");
    await act(async () => resolve("후보"));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByTestId("data")).toHaveTextContent("후보");
  });

  it("[취소] 는 요청을 끊고 이전 결과를 그대로 둔다", async () => {
    let n = 0;
    const signals: AbortSignal[] = [];
    const fn = (_a: string, s: AbortSignal) => {
      signals.push(s);
      n += 1;
      if (n === 1) return Promise.resolve("첫 결과");
      return new Promise<string>((_r, reject) => s.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
    };
    render(<Harness fn={fn} />);
    await act(async () => fireEvent.click(screen.getByText("시작")));
    expect(screen.getByTestId("data")).toHaveTextContent("첫 결과");
    fireEvent.click(screen.getByText("시작"));
    expect(screen.getByRole("status")).toBeInTheDocument();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "취소" })));
    expect(signals[1]!.aborted).toBe(true);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByTestId("data")).toHaveTextContent("첫 결과");
    expect(screen.getByTestId("state")).toHaveTextContent("취소됨");
  });

  it("오류는 error 에 남고 run 은 던지지 않는다", async () => {
    render(<Harness fn={() => Promise.reject(new Error("x"))} />);
    await act(async () => fireEvent.click(screen.getByText("시작")));
    expect(screen.getByTestId("state")).toHaveTextContent("오류");
  });
});
