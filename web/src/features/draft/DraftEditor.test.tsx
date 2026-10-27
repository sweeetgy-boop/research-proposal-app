import * as React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DraftEditor } from "./DraftEditor";
import { emptyEditState, toEditRequest, usableRevisions, type EditState } from "./editModel";
import { expectNoA11yViolations } from "@/test/utils";
import version1 from "@/test/fixtures/version1.json";
import finalReview from "@/test/fixtures/final_review.json";
import type { ReviewOut, VersionOut } from "@/api/types";

const v = version1 as unknown as VersionOut;
const review = finalReview as unknown as ReviewOut;

function Harness({ onState }: { onState?: (s: EditState) => void }) {
  const [state, setState] = React.useState<EditState>(emptyEditState);
  const revisions = React.useMemo(() => usableRevisions(review.comments), []);
  return (
    <DraftEditor
      sections={v.sections}
      annotations={[{ id: "r1-2", section: "method", sentence: null, sentence_id: null, kind: "section", text: "연차별 산출물을 적을 것", reason: null, status: "open" }]}
      revisions={revisions}
      state={state}
      onChange={(s) => {
        setState(s);
        onState?.(s);
      }}
    />
  );
}

describe("DraftEditor", () => {
  it("섹션 제목과 문장, 출처 배지를 그린다", () => {
    render(<Harness />);
    expect(screen.getByRole("heading", { name: "2-다 연구 방법 및 주요내용" })).toBeInTheDocument();
    expect(screen.getAllByText("로컬 작성").length).toBeGreaterThan(0);
  });

  it("수정안 사용 → use_revision + comment_id", async () => {
    let last: EditState = emptyEditState();
    render(<Harness onState={(s) => (last = s)} />);
    const group = screen.getByRole("radiogroup", { name: "2-다 연구 방법 및 주요내용 문장 1 처리" });
    await userEvent.click(within(group).getByLabelText("수정안 사용"));
    expect(screen.getByText(/경부선 구간의 검측 이력/)).toBeInTheDocument();
    const req = toEditRequest(last, 1, usableRevisions(review.comments));
    expect(req.sentences).toEqual([{ sentence_id: "s:method:0", action: "use_revision", comment_id: "r2-1" }]);
  });

  it("직접 수정·삭제·뒤에 추가", async () => {
    let last: EditState = emptyEditState();
    render(<Harness onState={(s) => (last = s)} />);
    const groups = screen.getAllByRole("radiogroup");
    const objective = groups.find((g) => within(g).queryByLabelText("수정안 사용") === null)!;
    await userEvent.click(within(objective).getByLabelText("직접 수정"));
    const ta = screen.getByRole("textbox", { name: /직접 수정/ });
    await userEvent.clear(ta);
    await userEvent.type(ta, "고친 문장임.");
    await userEvent.click(within(objective).getByLabelText("삭제"));
    await userEvent.click(screen.getAllByRole("button", { name: "뒤에 문장 추가" })[0]!);
    await userEvent.type(screen.getByRole("textbox", { name: /이 문장 뒤에 추가/ }), "추가 문장임.");
    const req = toEditRequest(last, 1, new Map());
    const actions = (req.sentences ?? []).map((s) => s.action);
    expect(actions).toContain("delete");
    expect(actions).toContain("insert_after");
    expect(req.sentences?.find((s) => s.action === "insert_after")?.text).toBe("추가 문장임.");
  });

  it("섹션 통문 편집을 켜면 문장 선택이 잠긴다", async () => {
    render(<Harness />);
    const before = screen.getAllByRole("radiogroup").length;
    await userEvent.click(screen.getAllByLabelText("섹션 전체를 통문으로 편집")[0]!);
    expect(screen.getAllByRole("radiogroup").length).toBeLessThan(before);
    expect(screen.getByRole("textbox", { name: /통문/ })).toBeInTheDocument();
  });

  it("메모 처리됨", async () => {
    let last: EditState = emptyEditState();
    render(<Harness onState={(s) => (last = s)} />);
    await userEvent.click(screen.getByLabelText("처리됨"));
    expect(last.doneAnnotations).toEqual(["r1-2"]);
  });

  it("접근성 위반 없음", async () => {
    const { container } = render(<Harness />);
    await expectNoA11yViolations(container);
  });
});
