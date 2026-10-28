/** 레인 D 항목 21·22·25 — 아래 이동 막대(이전·다음·남은 일·한 번 알림), 위쪽 단계·탭·막대가 같은 단계,
 *  "변경 n건 · 확인 n건", 버전 목록의 확인 기록 접기, 화면 문구에 run 없음. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { expectNoA11yViolations, mockFetch, renderWithProviders } from "@/test/utils";
import RunLayout from "@/routes/run/RunLayout";
import Versions from "@/routes/run/Versions";
import { StepNavBar } from "@/components/StepNavBar";
import { ChangeCount } from "@/features/versions/SaveVersionFlow";
import { foldVersions } from "@/features/versions/fold";
import { remainingWork, runStepNeighbors } from "@/lib/runSteps";
import runFx from "@/test/fixtures/run_drafted.json";
import type { RunState, VersionRowMeta } from "@/api/types";

afterEach(() => vi.unstubAllGlobals());
const id = runFx.run_id;
const run = runFx as unknown as RunState;

function Page({ name }: { name: string }) {
  return <p>{name} 화면</p>;
}

function renderRun(route: string, routes: Record<string, unknown> = {}) {
  mockFetch({ [`/v1/runs/${id}`]: runFx, [`/v1/runs/${id}/submit-check`]: CHECK, ...routes });
  return renderWithProviders(
    <Routes>
      <Route path="/runs/:id" element={<RunLayout />}>
        <Route index element={<Page name="진행" />} />
        <Route path="idea" element={<Page name="입력" />} />
        <Route path="precheck" element={<Page name="유사과제" />} />
        <Route path="draft" element={<Page name="초안" />} />
        <Route path="edit" element={<Page name="수정" />} />
        <Route path="versions" element={<Versions />} />
        <Route path="final-review" element={<Page name="최종 검토" />} />
        <Route path="submit-check" element={<Page name="점검" />} />
        <Route path="finalize" element={<Page name="마무리" />} />
      </Route>
    </Routes>,
    { route, path: "*" },
  );
}

const CHECK = {
  run_id: id,
  ok: false,
  items: [
    { key: "figures_unconfirmed", label: "확인 전 그림", ok: false, detail: "", count: 1, target: null },
    { key: "figures_undecided", label: "결정 전 추천 그림", ok: false, detail: "", count: 1, target: null },
    { key: "local_review_mismatch", label: "로컬 검토 불일치", ok: false, detail: "", count: 2, target: null },
    { key: "required_sections", label: "필수 섹션", ok: true, detail: "", count: 0, target: null },
  ],
};

const textHasNoRun = (el: HTMLElement) => expect(el.textContent ?? "").not.toMatch(/\brun\b/i);

describe("아래 이동 막대", () => {
  it("남은 일 요약은 막지 않고, 넘어갈 때 한 번만 알린다", async () => {
    const onNext = vi.fn();
    renderWithProviders(
      <StepNavBar prev={{ label: "이전 단계: 초안 생성", to: "/x" }} next={{ label: "다음: 최종 검토", onClick: onNext }} remaining={["확인 전 그림 1장"]} noticeKey="t1" />,
    );
    expect(screen.getByTestId("stepnav-remaining")).toHaveTextContent("남은 일: 확인 전 그림 1장");
    await userEvent.click(screen.getByRole("button", { name: "다음: 최종 검토" }));
    expect(onNext).toHaveBeenCalledTimes(1);
    const first = (await screen.findAllByText(/남은 일이 있습니다: 확인 전 그림 1장/)).length;
    expect(first).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "다음: 최종 검토" }));
    expect(onNext).toHaveBeenCalledTimes(2);
    expect(screen.getAllByText(/남은 일이 있습니다/).length).toBe(first); // 두 번째는 알림 없음
    expect(document.documentElement.style.getPropertyValue("--stepnav-h")).toMatch(/px$/);
  });

  it("막힌 다음 단계는 이유를 보이고 누를 수 없다 (② 게이트)", () => {
    renderWithProviders(<StepNavBar next={{ label: "다음: 선행연구 브리핑", onClick: () => {}, reason: "차단 행을 골라 주십시오" }} />);
    const next = screen.getByRole("button", { name: "다음: 선행연구 브리핑" });
    expect(next).toBeDisabled();
    expect(next).toHaveAccessibleDescription("차단 행을 골라 주십시오");
  });

  it("remainingWork: 실패 항목만, 그림은 장·결정은 건, 레인 B 항목은 이름 그대로", () => {
    expect(remainingWork(CHECK.items)).toEqual(["확인 전 그림 1장", "추천 그림 결정 1건", "로컬 검토 불일치 2건"]);
    expect(remainingWork(CHECK.items, 2)).toEqual(["확인 전 그림 1장", "추천 그림 결정 1건", "외 1건"]);
  });

  it("위쪽 단계·탭·막대가 같은 단계를 가리킨다 (runStepNeighbors)", async () => {
    const { container } = renderRun(`/runs/${id}/draft`);
    const steps = await screen.findByRole("navigation", { name: "작성 단계" });
    const bar = screen.getByRole("navigation", { name: "단계 이동" });
    expect(within(steps).getByRole("link", { name: /3단계 진행 중:\s*초안 생성/ })).toHaveAttribute("aria-current", "step");
    expect(within(bar).getByRole("button", { name: "이전 단계: 유사과제 확인" })).toBeEnabled();
    expect(await within(bar).findByTestId("stepnav-remaining")).toHaveTextContent("확인 전 그림 1장 · 추천 그림 결정 1건 · 로컬 검토 불일치 2건");
    await userEvent.click(within(bar).getByRole("button", { name: "다음: 직접 수정" }));
    expect(await screen.findByText("수정 화면")).toBeInTheDocument();
    const tabs = screen.getByRole("navigation", { name: "제안서 화면 메뉴" });
    expect(within(tabs).getByRole("link", { name: "직접 수정" })).toHaveAttribute("aria-current", "page");
    expect(within(steps).getByRole("link", { name: /4단계 진행 중:\s*직접 수정/ })).toHaveAttribute("aria-current", "step");
    // ⑥ 은 아직 못 연다 — ⑤ 화면의 다음 단추가 이유를 보인다
    await userEvent.click(within(bar).getByRole("button", { name: "다음: 최종 검토" }));
    expect(await screen.findByText("최종 검토 화면")).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "다음: 최종 마무리" })).toHaveAccessibleDescription("최종 검토 후 열립니다");
    const n = runStepNeighbors(run, "versions");
    expect([n.current, n.prev?.to, n.next?.to]).toEqual([4, "draft", "final-review"]);
    textHasNoRun(document.body);
    await expectNoA11yViolations(container);
  });
});

describe("변경·확인 세기와 버전 목록", () => {
  it("변경 n건 · 확인 n건", () => {
    renderWithProviders(
      <ChangeCount
        local={0}
        server={{ run_id: id, base_version: 2, current_version: 2, total: 0, items: [], confirmations: 3, confirm_items: [{ type: "figure_confirm", label: "그림 확인", count: 3 }] }}
      />,
    );
    expect(screen.getByTestId("change-count")).toHaveTextContent("변경 0건");
    expect(screen.getByTestId("confirm-count")).toHaveTextContent("확인 3건");
  });

  const V = (n: number, extra: Partial<VersionRowMeta> = {}): VersionRowMeta => ({
    version: n,
    origin: n === 1 ? "local" : "edit",
    origin_label: n === 1 ? "Argon 작성(일부 로컬)" : "제안자 편집",
    created_at: "2026-10-28T01:00:00+00:00",
    based_on_review: null,
    reverted_from: null,
    note: "",
    changed_sections: [],
    alerts: 0,
    open_annotations: 0,
    figures: 3,
    ...extra,
  });

  it("예전 상태만 바뀐 버전은 '확인 기록' 으로 접고, v1 은 실제 작성자 배지", async () => {
    const versions = [
      V(1, { description: "초안 작성" }),
      V(2, { status_only: true, note: "그림 confirm", description: "그림 확인 — 연구 개념도", marks: ["그림 확인 — 연구 개념도"] }),
      V(3, { status_only: true, note: "그림 confirm", description: "그림 확인 — 분석 기법 그림 – SWOT 분석", marks: ["그림 확인 — 분석 기법 그림 – SWOT 분석"] }),
      V(4, { note: "수정", description: "수정", changed_sections: ["method"], marks: ["근거 승인"], confirmations: 1 }),
    ];
    expect(foldVersions(versions).map((r) => r.kind)).toEqual(["version", "fold", "version"]);
    const { container } = renderRun(`/runs/${id}/versions`, {
      [`/v1/runs/${id}/versions`]: { run_id: id, versions },
      [`/v1/runs/${id}/versions/diff`]: { run_id: id, from: 3, to: 4, sections: [], figures_changed: [] },
    });
    expect(await screen.findByText("Argon 작성(일부 로컬)")).toBeInTheDocument();
    const fold = screen.getByTestId("status-fold");
    expect(fold).toHaveTextContent("확인 기록 v2~v3 · 2건");
    expect(screen.queryByText("그림 confirm")).not.toBeInTheDocument();
    expect(screen.getByTestId("version-v4")).toHaveTextContent("바뀐 섹션:");
    expect(screen.getByTestId("marks-v4")).toHaveTextContent("확인 1건");
    textHasNoRun(container);
    await expectNoA11yViolations(container);
  });
});
