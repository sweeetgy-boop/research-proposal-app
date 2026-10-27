import { Moon, Sun } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";

type Theme = "light" | "dark";

function current(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") return attr;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = React.useState<Theme>(() => current());
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("rra-theme", next);
    } catch {
      /* ignore */
    }
    setTheme(next);
  };
  const label = theme === "dark" ? "밝은 테마로 바꾸기" : "어두운 테마로 바꾸기";
  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label={label} title={label} aria-pressed={theme === "dark"}>
      {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
    </Button>
  );
}
