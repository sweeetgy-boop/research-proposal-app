import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts", "playwright-report", "test-results"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // 보안: 비신뢰 텍스트(초안·검토 의견·청크)를 HTML 로 넣지 않는다
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "dangerouslySetInnerHTML 금지 — 비신뢰 텍스트는 UntrustedText 로만 표시한다.",
        },
      ],
    },
  },
  {
    // shadcn 식 variant 상수를 같은 파일에서 내보낸다 (fast refresh 경고 제외)
    files: ["src/components/ui/*.tsx", "src/features/versions/DiffView.tsx"],
    rules: { "react-refresh/only-export-components": "off" },
  },
);
