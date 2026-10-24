"""Tests for cost estimation from pricing table."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentops.db import connect
from agentops.ingest import ingest_run
from agentops.pricing import estimate_cost_usd, load_rates


class TestPricing(unittest.TestCase):
    def test_estimate_known_model(self) -> None:
        cost = estimate_cost_usd(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        self.assertAlmostEqual(cost or 0, 0.75)

    def test_caller_cost_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agentops.db")
            try:
                ingest_run(
                    conn,
                    {
                        "id": "c1",
                        "project": "demo",
                        "agent": "a",
                        "environment": "dev",
                        "name": "t",
                        "status": "ok",
                        "started_at": "2026-10-24T10:00:00+00:00",
                        "ended_at": "2026-10-24T10:00:01+00:00",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "input_tokens": 1_000_000,
                        "output_tokens": 0,
                        "cost_usd": 9.99,
                    },
                )
                row = conn.execute(
                    "SELECT cost_usd FROM runs WHERE id = ?", ("c1",)
                ).fetchone()
                self.assertEqual(row["cost_usd"], 9.99)
            finally:
                conn.close()

    def test_ingest_estimates_when_cost_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "agentops.db")
            try:
                ingest_run(
                    conn,
                    {
                        "id": "c2",
                        "project": "demo",
                        "agent": "a",
                        "environment": "dev",
                        "name": "t",
                        "status": "ok",
                        "started_at": "2026-10-24T10:00:00+00:00",
                        "ended_at": "2026-10-24T10:00:01+00:00",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "input_tokens": 1_000_000,
                        "output_tokens": 0,
                    },
                )
                row = conn.execute(
                    "SELECT cost_usd FROM runs WHERE id = ?", ("c2",)
                ).fetchone()
                self.assertAlmostEqual(row["cost_usd"], 0.15)
            finally:
                conn.close()

    def test_custom_pricing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.json"
            path.write_text(
                json.dumps({"acme/fast": {"input": 1.0, "output": 2.0}}),
                encoding="utf-8",
            )
            rates = load_rates(path)
            cost = estimate_cost_usd(
                provider="acme",
                model="fast",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                rates=rates,
            )
            self.assertAlmostEqual(cost or 0, 3.0)


if __name__ == "__main__":
    unittest.main()
