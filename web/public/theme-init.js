// 첫 그리기 전에 저장된 테마를 적용한다 (CSP 때문에 인라인 스크립트 대신 외부 파일).
// 저장값이 없으면 OS 설정(prefers-color-scheme)을 CSS 가 따른다.
(function () {
  try {
    var t = localStorage.getItem("rra-theme");
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  } catch (e) {
    /* 저장소 접근 불가 — 기본 테마 */
  }
})();
