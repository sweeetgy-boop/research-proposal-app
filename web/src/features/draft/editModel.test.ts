import type { ReviewComment, VersionSection } from "@/api/types";
import { countChanges, emptyEditState, fromWorking, isDirty, previewTexts, splitSentences, toEditRequest, toWorking, usableRevisions } from "./editModel";

const sections: VersionSection[] = [
  {
    key: "method",
    choices: [],
    sentences: [
      { sentence_id: "s:method:0", text: "첫 문장임.", evidence: ["a#0"], origin: "llm", source: "retrieved" },
      { sentence_id: "s:method:1", text: "둘째 문장임.", evidence: [], origin: "llm", source: "proposer_input" },
    ],
  },
  { key: "objective", choices: [], sentences: [{ sentence_id: "s:objective:0", text: "목적임.", evidence: [], origin: "llm", source: "proposer_input" }] },
];
const comments: ReviewComment[] = [
  { id: "r2-1", section: "method", sentence: 0, sentence_id: "s:method:0", issue_type: "문장", comment: "모호", revised_text: "고친 첫 문장임.", evidence: [], status: "open", usable: true, discard_reason: null },
  { id: "r2-2", section: "method", sentence: null, sentence_id: null, issue_type: "일관성", comment: "섹션 의견", revised_text: null, evidence: [], status: "open", usable: false, discard_reason: null },
];

describe("editModel", () => {
  const revisions = usableRevisions(comments);

  it("usable 수정안만 문장별로 모은다", () => {
    expect([...revisions.keys()]).toEqual(["s:method:0"]);
  });

  it("빈 상태는 dirty 아님, 변경 0", () => {
    expect(isDirty(emptyEditState())).toBe(false);
    expect(countChanges(emptyEditState())).toBe(0);
  });

  it("문장 선택 → EditRequest (바뀐 것만, base_version 포함)", () => {
    const state = emptyEditState();
    state.sentences["s:method:0"] = { action: "use_revision" };
    state.sentences["s:method:1"] = { action: "manual", text: " 직접 고침. " , inserted: "뒤에 추가함." };
    state.sentences["s:objective:0"] = { action: "delete" };
    state.note = "메모";
    state.doneAnnotations = ["r2-2"];
    const req = toEditRequest(state, 3, revisions);
    expect(req.base_version).toBe(3);
    expect(req.note).toBe("메모");
    expect(req.done_annotations).toEqual(["r2-2"]);
    expect(req.sentences).toEqual([
      { sentence_id: "s:method:0", action: "use_revision", comment_id: "r2-1" },
      { sentence_id: "s:method:1", action: "manual", text: "직접 고침." },
      { sentence_id: "s:method:1", action: "insert_after", text: "뒤에 추가함." },
      { sentence_id: "s:objective:0", action: "delete" },
    ]);
    expect(countChanges(state)).toBe(4);
  });

  it("미리보기 텍스트 = 임시 저장 본문", () => {
    const state = emptyEditState();
    state.sentences["s:method:0"] = { action: "use_revision" };
    state.sentences["s:method:1"] = { action: "delete", inserted: "새 문장임." };
    expect(previewTexts(sections, state, revisions)).toEqual({ method: ["고친 첫 문장임.", "새 문장임."], objective: ["목적임."] });
    const w = toWorking(sections, state, 2, revisions);
    expect(w.base_version).toBe(2);
    expect(w.sections?.[0]).toEqual({ section: "method", texts: ["고친 첫 문장임.", "새 문장임."] });
  });

  it("섹션 통문 편집은 문장 편집보다 우선", () => {
    const state = emptyEditState();
    state.sentences["s:method:0"] = { action: "delete" };
    state.sectionText["method"] = "하나임.\n둘임.";
    const req = toEditRequest(state, 1, revisions);
    expect(req.sentences).toEqual([]);
    expect(req.sections).toEqual([{ section: "method", text: "하나임.\n둘임.", texts: [], order: null }]);
    expect(previewTexts(sections, state, revisions).method).toEqual(["하나임.", "둘임."]);
  });

  it("임시 저장 복원: 달라진 섹션만 통문으로", () => {
    const state = fromWorking({ note: "n", sections: [{ section: "method", texts: ["첫 문장임.", "둘째 문장임."] }, { section: "objective", texts: ["바뀐 목적임."] }] }, sections);
    expect(state.note).toBe("n");
    expect(Object.keys(state.sectionText)).toEqual(["objective"]);
  });

  it("splitSentences: 줄바꿈 우선, 종결부호 뒤 분리", () => {
    expect(splitSentences("하나임. 둘임.\n셋임.")).toEqual(["하나임.", "둘임.", "셋임."]);
  });
});
