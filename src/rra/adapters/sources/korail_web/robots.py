"""robots.txt 해석 (표준 라이브러리 urllib.robotparser). 비어 있으면 모두 허용."""

from __future__ import annotations

from urllib.robotparser import RobotFileParser


class RobotsRules:
    def __init__(self, text: str | None, *, user_agent: str):
        self.user_agent = user_agent
        self.text = text or ""
        self._parser = RobotFileParser()
        self._parser.parse(self.text.splitlines())

    @property
    def empty(self) -> bool:
        return not self.text.strip()

    def allowed(self, url: str) -> bool:
        if self.empty:
            return True
        # 제품 토큰(첫 단어)으로 판정 — "RRA research-proposal-app (…)" → "RRA"
        token = self.user_agent.split()[0] if self.user_agent.split() else "*"
        return self._parser.can_fetch(token, url) and self._parser.can_fetch(self.user_agent, url)

    def crawl_delay(self) -> float | None:
        if self.empty:
            return None
        token = self.user_agent.split()[0] if self.user_agent.split() else "*"
        delay = self._parser.crawl_delay(token)
        return float(delay) if delay else None
