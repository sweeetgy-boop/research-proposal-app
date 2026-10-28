"""메모리 저장소 — RunStorePort·DocumentRepository·RunLogPort 의 결정적 구현 (가짜 모드 전용)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from rra.application.ports import RunBusy, RunNotFound
from rra.domain.models import Chunk, Document, RunState, StepRecord

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self.docs: dict[str, Document] = {}
        self.chunks: list[Chunk] = []
        self.ingested: dict[str, str] = {}

    def seed(self, docs: list[Document], chunks: list[Chunk], *, when: str = "") -> None:
        for d in docs:
            self.docs[d.doc_id] = d
            self.ingested[d.source] = when
        self.chunks.extend(chunks)

    async def upsert(self, docs, chunks):
        self.seed(docs, chunks, when=date.today().isoformat())

    def _valid(self, doc_id: str) -> bool:
        doc = self.docs.get(doc_id)
        return doc is None or doc.is_valid_on(date.today())

    async def hybrid_search(self, queries, *, k=20, orgs=None, sources=None):
        if not [q for q in queries if isinstance(q, str) and q.strip()]:
            return []
        hits = [c for c in self.chunks if self._valid(c.doc_id)]
        if sources:
            hits = [c for c in hits if c.doc_id.split(":", 1)[0] in set(sources)]
        return hits[: max(0, k)]

    async def find_similar(self, text, *, k=10, sources=None):
        query = set(_TOKEN.findall((text or "").lower()))
        if not query:
            return []
        best: dict[str, float] = {}
        chunked = {c.doc_id for c in self.chunks}
        texts = [(c.doc_id, c.text) for c in self.chunks] + [
            # 청크 없는 문서(예: NTIS 과제)는 제목·초록으로 — precheck 에만 잡힌다
            (d.doc_id, " ".join(p for p in (d.title, d.abstract, d.body) if p))
            for d in self.docs.values()
            if d.doc_id not in chunked
        ]
        for doc_id, text in texts:
            if not self._valid(doc_id):
                continue
            tokens = set(_TOKEN.findall(text.lower()))
            score = len(query & tokens) / len(query | tokens) if tokens else 0.0
            if score > 0 and score > best.get(doc_id, 0.0):
                best[doc_id] = score
        if sources:
            best = {d: s for d, s in best.items() if d.split(":", 1)[0] in set(sources)}
        ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[: max(0, k)]
        return [(self.docs[d], s) for d, s in ranked if d in self.docs]

    async def get_document(self, doc_id):
        return self.docs.get(doc_id)

    async def count_by_source(self):
        out: dict[str, int] = {}
        for d in self.docs.values():
            out[d.source] = out.get(d.source, 0) + 1
        return out

    async def source_status(self):
        counts = await self.count_by_source()
        return {
            s: {"count": n, "last_ingested": self.ingested.get(s) or None}
            for s, n in counts.items()
        }


class _Claim:
    def __init__(self, store: InMemoryRunStore, key: tuple[str, str]):
        self.store, self.key = store, key

    def release(self) -> None:
        self.store.claimed.discard(self.key)


class InMemoryRunStore:
    def __init__(self) -> None:
        self.states: dict[tuple[str, str], RunState] = {}
        self.requests: dict[tuple[str, str], Any] = {}
        self.snapshots: dict[tuple[str, str], Any] = {}
        self.sections: dict[tuple[str, str], dict[str, Any]] = {}
        self.drafts: dict[tuple[str, str], Any] = {}
        self.confirmations: dict[tuple[str, str], Any] = {}
        self.versions: dict[tuple[str, str], dict[int, Any]] = {}
        self.reviews: dict[tuple[str, str], dict[int, Any]] = {}
        self._recommendations: dict[tuple[str, str], dict[str, Any]] = {}
        self._working: dict[tuple[str, str], dict[str, Any]] = {}
        self._outlines: dict[tuple[str, str], dict[str, Any]] = {}
        self._candidates: dict[tuple[str, str], dict[str, Any]] = {}
        self._figure_images: dict[tuple[str, str], dict[str, tuple[bytes, str]]] = {}
        self.rewrites: dict[tuple[str, str], dict[str, Any]] = {}
        self.notes: dict[tuple[str, str], dict[str, Any]] = {}
        self.usage: dict[tuple[str, str], Any] = {}
        self.claimed: set[tuple[str, str]] = set()
        self._seq = 0

    def _key(self, user, run_id):
        if (user, run_id) not in self.states:
            raise RunNotFound(run_id)
        return (user, run_id)

    def create(self, user, req, steps, now):
        self._seq += 1
        run_id = (
            f"{now[:4]}0101000000-{self._seq:08x}"
            if len(now) >= 4
            else f"20260101000000-{self._seq:08x}"
        )
        state = RunState(
            run_id=run_id,
            user=user,
            steps=[StepRecord(name=n) for n in steps],
            created_at=now,
            updated_at=now,
        )
        self.states[(user, run_id)] = state.model_copy(deep=True)
        self.requests[(user, run_id)] = req
        return state

    def load_state(self, user, run_id):
        return self.states[self._key(user, run_id)].model_copy(deep=True)

    def save_state(self, state):
        self.states[(state.user, state.run_id)] = state.model_copy(deep=True)

    def load_request(self, user, run_id):
        return self.requests[self._key(user, run_id)]

    def save_snapshot(self, user, run_id, snapshot):
        self.snapshots[self._key(user, run_id)] = snapshot

    def load_snapshot(self, user, run_id):
        return self.snapshots.get((user, run_id))

    def save_section(self, user, run_id, section):
        self.sections.setdefault(self._key(user, run_id), {})[section.key] = section

    def load_sections(self, user, run_id):
        return dict(self.sections.get(self._key(user, run_id), {}))

    def save_draft(self, user, run_id, draft):
        self.drafts[self._key(user, run_id)] = draft

    def save_confirmation(self, user, run_id, confirmation):
        self.confirmations[self._key(user, run_id)] = confirmation

    def load_confirmation(self, user, run_id):
        return self.confirmations.get((user, run_id))

    def save_version(self, user, run_id, version):
        self.versions.setdefault(self._key(user, run_id), {})[version.version] = version

    def load_version(self, user, run_id, version):
        return self.versions.get(self._key(user, run_id), {}).get(version)

    def list_versions(self, user, run_id):
        return sorted(self.versions.get(self._key(user, run_id), {}))

    def save_outline(self, user, run_id, data):
        self._outlines[(user, run_id)] = dict(data)

    def load_outline(self, user, run_id):
        return self._outlines.get((user, run_id))

    def save_figure_image(self, user, run_id, sha, data, mime):
        self._figure_images.setdefault((user, run_id), {})[sha] = (bytes(data), mime)

    def load_figure_image(self, user, run_id, sha):
        return self._figure_images.get((user, run_id), {}).get(sha)

    def save_candidates(self, user, run_id, data):
        self._candidates[(user, run_id)] = dict(data)

    def load_candidates(self, user, run_id):
        return self._candidates.get((user, run_id))

    def save_working(self, user, run_id, data):
        self._working[(user, run_id)] = dict(data)

    def load_working(self, user, run_id):
        return self._working.get((user, run_id))

    def clear_working(self, user, run_id):
        self._working.pop((user, run_id), None)

    def save_recommendations(self, user, run_id, data):
        self._recommendations[(user, run_id)] = dict(data)

    def load_recommendations(self, user, run_id):
        return self._recommendations.get((user, run_id))

    def save_rewrite(self, user, run_id, key, data):
        self.rewrites.setdefault(self._key(user, run_id), {})[key] = dict(data)

    def load_rewrite(self, user, run_id, key):
        return self.rewrites.get(self._key(user, run_id), {}).get(key)

    def clear_rewrite(self, user, run_id, key):
        self.rewrites.get(self._key(user, run_id), {}).pop(key, None)

    def save_notes(self, user, run_id, data):
        self.notes[self._key(user, run_id)] = dict(data)

    def load_notes(self, user, run_id):
        return self.notes.get(self._key(user, run_id))

    def save_usage(self, user, run_id, usage):
        self.usage[self._key(user, run_id)] = usage.model_copy(deep=True)

    def load_usage(self, user, run_id):
        return self.usage.get(self._key(user, run_id))

    def save_review(self, user, run_id, review):
        self.reviews.setdefault(self._key(user, run_id), {})[review.round] = review

    def load_review(self, user, run_id, round_no):
        return self.reviews.get(self._key(user, run_id), {}).get(round_no)

    def list_reviews(self, user, run_id):
        return sorted(self.reviews.get(self._key(user, run_id), {}))

    def list_runs(self, user, limit=50):
        runs = [s for (u, _), s in self.states.items() if u == user]
        return [s.model_copy(deep=True) for s in sorted(runs, key=lambda s: s.run_id)][-limit:]

    def claim(self, user, run_id):
        key = self._key(user, run_id)
        if key in self.claimed:
            raise RunBusy(run_id)
        self.claimed.add(key)
        return _Claim(self, key)

    def is_alive(self, user, run_id):
        return (user, run_id) in self.claimed

    def list_users(self):
        return sorted({u for (u, _) in self.states})

    def delete_run(self, user, run_id):
        key = self._key(user, run_id)
        for table in (
            self.states,
            self.requests,
            self.snapshots,
            self.sections,
            self.drafts,
            self.confirmations,
            self.versions,
            self.reviews,
        ):
            table.pop(key, None)


class NoopRunLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, run_id, manifest):
        self.records.append((run_id, manifest))
