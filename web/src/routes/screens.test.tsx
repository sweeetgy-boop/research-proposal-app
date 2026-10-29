/** 화면 단위: 가짜 응답(fixtures)으로 그리고 axe 를 돌린다. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations, mockFetch, problem, renderWithProviders } from "@/test/utils";
import { clearSession, getCsrf } from "@/auth/session";
import { resetIdea, updateIdea } from "@/features/idea/store";
import { emptyRequest } from "@/lib/validation";
import Login from "./Login";
import Precheck from "./Precheck";
import Runs from "./Runs";
import RunLayout from "./run/RunLayout";
import Draft from "./run/Draft";
import Finalize from "./run/Finalize";
import precheckFx from "@/test/fixtures/precheck.json";
import draftFx from "@/test/fixtures/draft.json";
import reviewFx from "@/test/fixtures/draft_review.json";
import runFx from "@/test/fixtures/run_final_reviewed.json";
import runsFx from "@/test/fixtures/runs.json";
import checkFx from "@/test/fixtures/render_check.json";
import type { PrecheckOut } from "@/api/types";
import { Route, Routes } from "react-router";
import { Layout } from "@/components/Layout";

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
  resetIdea();
});

describe("로그인", () => {
  const FAILED = "사번 또는 아이디·비밀번호를 확인하세요";
  function sessionMock() {
    return mockFetch({
      "/v1/session": (init?: RequestInit) => {
        const body = JSON.parse(String(init?.body)) as { kind: string; token?: string; staff_no?: string; id?: string; password?: string };
        if (body.kind === "token") return body.token === "good" ? { csrf: "c1", expires_in: 10, kind: "admin", label: "관리자" } : problem(401, "인증 토큰이 맞지 않습니다.");
        if (body.kind === "staff") return body.staff_no === "K-0001" ? { csrf: "c2", expires_in: 10, kind: "staff", label: "직원" } : problem(401, FAILED);
        return body.id === "team" && body.password === "pw" ? { csrf: "c3", expires_in: 10, kind: "guest", label: "공용 계정" } : problem(401, FAILED);
      },
    });
  }

  it("직원 탭: 사번만 보내고 CSRF·종류만 보관, 틀리면 통일된 문구 (axe 0)", async () => {
    const { calls } = sessionMock();
    const { container } = renderWithProviders(<Login />, { route: "/login" });
    await expectNoA11yViolations(container);
    expect(screen.getByRole("tab", { name: "철도연구원 직원(사번)" })).toHaveAttribute("aria-selected", "true");
    await userEvent.type(screen.getByLabelText("사번"), "K-9999");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByText(FAILED)).toBeInTheDocument();
    expect(getCsrf()).toBeNull();
    expect(screen.getByLabelText("사번")).toHaveValue(""); // 실패 뒤 입력값 삭제
    await userEvent.type(screen.getByLabelText("사번"), "K-0001");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(getCsrf()).toBe("c2"));
    expect(sessionStorage.getItem("rra-session-kind")).toBe("직원");
    expect(JSON.stringify(sessionStorage)).not.toContain("K-0001"); // 사번은 저장하지 않는다
    expect(calls.every((c) => !String(c.url).includes("K-0001"))).toBe(true);
  });

  it("그 외 사용자 탭: 아이디·비밀번호, 관리자 링크 아래 토큰 (axe 0)", async () => {
    sessionMock();
    const { container } = renderWithProviders(<Login />, { route: "/login" });
    await userEvent.click(screen.getByRole("tab", { name: "그 외 사용자(아이디·비밀번호)" }));
    await expectNoA11yViolations(container);
    await userEvent.type(screen.getByLabelText("아이디"), "team");
    await userEvent.type(screen.getByLabelText("비밀번호"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    expect(await screen.findByText(FAILED)).toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호")).toHaveValue("");
    await userEvent.type(screen.getByLabelText("비밀번호"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(getCsrf()).toBe("c3"));
    expect(sessionStorage.getItem("rra-session-kind")).toBe("공용 계정");
    clearSession();
    await userEvent.click(screen.getByRole("button", { name: "관리자" }));
    await expectNoA11yViolations(container);
    expect(screen.queryByRole("tablist")).toBeNull();
    await userEvent.type(screen.getByLabelText("관리자 접속 토큰"), "good");
    await userEvent.click(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(getCsrf()).toBe("c1"));
    expect(JSON.stringify(sessionStorage)).not.toContain("good");
  });
});

describe("유사과제 확인", () => {
  it("추천 0건·차단 아님: 알림 표와 다음 버튼, axe 통과", async () => {
    mockFetch({});
    updateIdea({ precheck: precheckFx as PrecheckOut, request: { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" } });
    const { container } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByRole("heading", { name: /유사과제 1건/ })).toBeInTheDocument();
    expect(screen.getByText("추천 0건")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /다음: 선행연구 브리핑/ })).toBeEnabled();
    await expectNoA11yViolations(container);
  });

  it("관련 연구는 판정 표와 분리된 '참고' 목록으로 보인다 (ADR 0028)", async () => {
    mockFetch({});
    const pre: PrecheckOut = {
      ...(precheckFx as PrecheckOut),
      related_research: [
        { doc_id: "scienceon:fake-1", title: "궤도 틀림 논문 (가짜)", source: "scienceon", source_label: "ScienceON 국내 논문·보고서", doc_type: "paper", year: 2024, similarity: 0.9123, url: "https://example.invalid/p1" },
        { doc_id: "ntis:rep-1", title: "국가R&D 보고서 (가짜)", source: "ntis", source_label: "NTIS 국가R&D 과제", doc_type: "report", year: null, similarity: 0.88, url: null },
      ],
    };
    updateIdea({ precheck: pre, request: { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" } });
    const { container } = renderWithProviders(<Precheck />, { route: "/new/precheck" });
    expect(screen.getByRole("heading", { name: /유사과제 1건/ })).toBeInTheDocument();
    const section = screen.getByRole("region", { name: /관련 연구 2건/ });
    expect(section).toHaveTextContent("궤도 틀림 논문 (가짜)");
    expect(section).toHaveTextContent("ScienceON 국내 논문·보고서 · 논문 · 2024");
    expect(section).not.toHaveTextContent(/유사도|scienceon:/); // 유사도 숫자·내부 번호 없음 (ADR 0039)
    expect(within(section).getAllByText("참고")).toHaveLength(2);
    expect(within(section).queryByText("차단")).toBeNull();
    const link = within(section).getByRole("link", { name: /원문/ });
    expect(link).toHaveAttribute("href", "https://example.invalid/p1");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("button", { name: /다음: 선행연구 브리핑/ })).toBeEnabled();
    await expectNoA11yViolations(container);
  });

  it("차단 경보는 확인란을 표시해야 다음으로 갈 수 있다", async () => {
    mockFetch({});
    const pre = { ...(precheckFx as PrecheckOut), blocking: true, alerts: (precheckFx as PrecheckOut).alerts.map((a) => ({ ...a, blocking: true })) };
    updateIdea({ precheck: pre, request: { ...emptyRequest(), current_state: "a", root_cause: "b", limitation: "c", goal: "d" } });
    renderWithProviders(<Precheck />, { route: "/new/precheck" });
    const next = screen.getByRole("button", { name: /다음: 선행연구 브리핑/ });
    expect(next).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/차단 경보를 확인했고/));
    expect(next).toBeEnabled();
  });
});

describe("run 화면", () => {
  const id = runFx.run_id;
  const routes = {
    [`/v1/runs/${id}`]: runFx,
    [`/v1/runs/${id}/draft`]: draftFx,
    [`/v1/runs/${id}/draft-review`]: reviewFx,
    [`/v1/runs/${id}/outline`]: problem(404, "설계도가 없습니다"),
    [`/v1/runs/${id}/render-check`]: checkFx,
    "/v1/runs": runsFx,
  };

  it("초안 보기: 섹션·출처 배지·1차 검토 패널, axe 통과", async () => {
    mockFetch(routes);
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/runs/:id" element={<RunLayout />}>
          <Route path="draft" element={<Draft />} />
        </Route>
      </Routes>,
      { route: `/runs/${id}/draft`, path: "*" },
    );
    expect(await screen.findByRole("heading", { name: "초안 본문" })).toBeInTheDocument();
    expect(await screen.findByText("2-다 연구 방법 및 주요내용")).toBeInTheDocument();
    expect(screen.getAllByText("Argon 보완").length).toBeGreaterThan(0);
    expect(await screen.findByRole("heading", { name: "Argon 1차 검토" })).toBeInTheDocument();
    expect(screen.getByText(/v2 에 1건 자동 반영/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("최종 마무리: 선택형·제안자 정보·렌더 점검, axe 통과", async () => {
    mockFetch(routes);
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/runs/:id" element={<RunLayout />}>
          <Route path="finalize" element={<Finalize />} />
        </Route>
      </Routes>,
      { route: `/runs/${id}/finalize`, path: "*" },
    );
    expect(await screen.findByRole("heading", { name: /최종 마무리/ })).toBeInTheDocument();
    expect(await screen.findByRole("radio", { name: "응용연구" })).toBeChecked();
    expect(screen.getByRole("button", { name: "HWPX 내려받기" })).toBeEnabled();
    expect(await screen.findByText(/알림 2건/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("run 목록: 표와 상태, axe 통과 (Layout 포함)", async () => {
    mockFetch(routes);
    const { container } = renderWithProviders(
      <Routes>
        <Route element={<Layout />}>
          <Route path="/runs" element={<Runs />} />
        </Route>
      </Routes>,
      { route: "/runs", path: "*" },
    );
    // 항목 2 — 과제 제목(두 줄 말줄임, 전체는 title)과 만든 때, run 번호는 작게
    const link = await screen.findByRole("link", { name: /검측 이력 기반 궤도 틀림/ });
    expect(link).toHaveClass("line-clamp-2");
    expect(link).toHaveAttribute("title", runsFx.runs[0]!.title);
    expect(screen.getAllByText(/만든 때 /).length).toBeGreaterThan(0); // 내 제안서 줄 정보 (UI Research Studio)
    expect(screen.getByText(id)).toBeInTheDocument();
    expect(screen.getAllByText("제목 미정").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "본문으로 건너뛰기" })).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });
});
