# ADR 0009 — 사내 과제 목록·공시자료는 공개 자료(public) (2026-10-26, PR #15)

**배경** P2 적재 때 사내 자료를 전부 internal 로 두어 외부 검토에 보내지 않았다.
**선택지** (a) 전부 internal, (b) 전부 public, (c) 공시된 것은 public, 공시용 요약이 없는 일반 요약만 internal.
**결정** (c). 엑셀 4개 과제 목록·공시용 요약문은 public, 일반 요약문만 있는 5건은 internal. own 티어는 source 로 판정(부서 무관).
**이유** 이미 공시(알리오)된 자료라 외부 전송 위험이 없고, 검토 품질에 사내 맥락이 필요.
**결과** dev DB own 1,119 public / alio 115 public·5 internal. 근거 `a8d4a0e`, architecture §4.8.
