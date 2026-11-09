"""말뭉치 IDF 표 JSON 캐시 (레인 E, ADR 0059) — `data/cache/idf.json`(경로는 조립이 준다).

형식: {"documents": N, "max_idf": x.xx, "values": {토큰: idf}}. 임시 파일에 쓴 뒤 교체(원자적), 권한
600.
토큰은 수집 문서에서 온 낱말(비신뢰)이라 글자만 들어 있지만 그대로 신뢰하지 않는다 — 읽을 때 숫자만
받는다."""

from __future__ import annotations

import json
import os
from pathlib import Path

from rra.domain.rules.idf import IdfWeights


class JsonIdfCache:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> IdfWeights | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
            return None
        values = {
            str(k): float(v)
            for k, v in data["values"].items()
            if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        if not values:
            return None
        docs = data.get("documents")
        return IdfWeights(
            values=values,
            documents=int(docs) if isinstance(docs, int) else 0,
            max_idf=max(values.values()),
        )

    def save(self, weights: IdfWeights) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {
                "documents": weights.documents,
                "max_idf": weights.max_idf,
                "values": dict(sorted(weights.values.items())),
            },
            ensure_ascii=False,
        )
        tmp = self.path.with_suffix(self.path.suffix + ".part")
        tmp.write_text(body, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)
