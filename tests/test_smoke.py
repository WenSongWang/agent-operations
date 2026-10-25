"""Smoke / fail-demo CLI checks."""

from __future__ import annotations

import unittest
from unittest import mock

from agentops.smoke import main, run_fail_demo


class TestSmoke(unittest.TestCase):
    def test_fail_demo_passes(self) -> None:
        self.assertEqual(run_fail_demo(), 0)

    def test_main_fail_demo_flag(self) -> None:
        with mock.patch("sys.argv", ["agentops-smoke", "--fail-demo"]):
            self.assertEqual(main(), 0)


if __name__ == "__main__":
    unittest.main()
