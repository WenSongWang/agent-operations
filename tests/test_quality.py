"""Tests for quality / eval fields on runs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentops.db import connect
from agentops.ingest import IngestError, ingest_run
from agentops.query import get_run


def _base(**overrides):
    payload = {
        "id": "run-1",
        "project": "demo",
        "agent": "assistant",
        "environment": "dev",
        "name": "hello",
        "status": "ok",
        "started_at": "2026-10-24T10:00:00+00:00",
        "ended_at": "2026-10-24T10:00:01+00:00",
    }
    payload.update(overrides)
    return payload


class TestQuality(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.conn = connect(Path(self._tmp.name) / "agentops.db")

    def tearDown(self) -> None:
        self.conn.close()
        self._tmp.cleanup()

    def test_quality_fields_stored(self) -> None:
        ingest_run(
            self.conn,
            _base(
                quality_score=0.85,
                thumbs="up",
                prompt_version="p-v3",
                template_version="tpl-2",
            ),
        )
        detail = get_run(self.conn, "run-1")
        assert detail is not None
        self.assertEqual(detail["quality_score"], 0.85)
        self.assertEqual(detail["thumbs"], "up")
        self.assertEqual(detail["prompt_version"], "p-v3")
        self.assertEqual(detail["template_version"], "tpl-2")

    def test_invalid_thumbs_rejected(self) -> None:
        with self.assertRaises(IngestError):
            ingest_run(self.conn, _base(thumbs="meh"))

    def test_quality_score_bounds(self) -> None:
        with self.assertRaises(IngestError):
            ingest_run(self.conn, _base(quality_score=1.5))

    def test_migrate_adds_columns_on_old_db(self) -> None:
        path = Path(self._tmp.name) / "old.db"
        raw = __import__("sqlite3").connect(str(path))
        raw.execute(
            "CREATE TABLE runs (id TEXT PRIMARY KEY, project TEXT, agent TEXT, "
            "environment TEXT, name TEXT, status TEXT, started_at TEXT, "
            "ended_at TEXT, ingested_at TEXT)"
        )
        raw.commit()
        raw.close()
        conn = connect(path)
        try:
            cols = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
            for name in (
                "quality_score",
                "thumbs",
                "prompt_version",
                "template_version",
            ):
                self.assertIn(name, cols)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
