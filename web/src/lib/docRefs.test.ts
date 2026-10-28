import { docRef, hasInternalId, refSource, refTitle, replaceDocIds, SOURCE_NAMES, sourceName, UNTITLED } from "./docRefs";

const refs = [
  { id: "own:2023-01#3", doc_id: "own:2023-01", title: "궤도 점검 과제", source: "own", source_label: "사내 과제" },
  { id: "alio:sum-0f3a12ab#1", doc_id: "alio:sum-0f3a12ab", title: "알리오 요약", source: "alio" },
];
const sec = (k: string) => ({ method: "연구방법", objective: "연구목표" })[k] ?? k;

describe("docRefs — 내부 번호 대신 제목·자료원 이름 (ADR 0040)", () => {
  it("자료원 이름 표 (서버 doc_refs.SOURCE_NAMES 와 같은 키)", () => {
    expect(sourceName("korail_web")).toBe("공사 홈페이지");
    expect(sourceName("openalex")).toBe("OpenAlex 논문");
    expect(sourceName("nope")).toBe("수집 자료");
    expect(Object.keys(SOURCE_NAMES)).toEqual(expect.arrayContaining(["own", "alio", "ntis", "scienceon", "molit", "bai", "rnd_notice"]));
  });

  it("docRef — 인용 목록에서 찾고, 없으면 자료원 이름만 (번호를 제목으로 쓰지 않는다)", () => {
    expect(docRef("own:2023-01#3", refs).title).toBe("궤도 점검 과제");
    expect(docRef("own:2023-01#9", refs).title).toBe("궤도 점검 과제"); // 같은 문서의 다른 청크
    const unknown = docRef("ntis:1711234#0", refs);
    expect(refTitle(unknown)).toBe(UNTITLED);
    expect(refSource(unknown)).toBe("NTIS 국가R&D");
    expect(refTitle({ title: "korail_web:99fc7ccfee790c87" })).toBe(UNTITLED);
  });

  it("replaceDocIds — 글 속 번호를 「제목」·일반 말로, 그림·문장 번호는 섹션 이름으로", () => {
    expect(replaceDocIds("근거 [own:2023-01#3] 와 다름", refs)).toBe("근거 「궤도 점검 과제」 와 다름");
    expect(replaceDocIds("출처(근거: alio:sum-0f3a12ab#1)를 보면", refs)).toBe("출처「알리오 요약」를 보면");
    expect(replaceDocIds("ntis:1711234 과제와 겹침", refs)).toBe("관련 자료 과제와 겹침");
    expect(replaceDocIds("sum-0f3a12ab 참고", refs)).toBe("「알리오 요약」 참고");
    expect(replaceDocIds("그림 f:method:t1 은 3단계, f:objective:2", refs, sec)).toBe("연구방법 분석 기법 그림 1 은 3단계, 연구목표 그림 2");
    expect(replaceDocIds("s:objective:0 문장이 길다", refs, sec)).toBe("연구목표 문장 1 문장이 길다");
    expect(replaceDocIds("(doc_id: openalex:W123#0) 인용", refs)).toBe("인용");
  });

  it("hasInternalId — e2e expectNoInternalIds 와 같은 기준", () => {
    for (const t of ["own:2023-01", "alio:sum-0f3a12ab", "korail_web:99fc7ccfee790c87#2", "f:method:t1", "s:policy_importance:0", "sum-0f3a12ab9"]) {
      expect(hasInternalId(t)).toBe(true);
    }
    for (const t of ["궤도 점검 과제", "2026년 9월 기준", "사내 과제 · 공사 홈페이지", "R&D 공고"]) expect(hasInternalId(t)).toBe(false);
  });
});
