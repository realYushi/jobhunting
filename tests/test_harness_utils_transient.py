import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from lib import harness_utils


class HarnessUtilsTransientTests(unittest.TestCase):
    def test_harness_env_skips_default_cdp_for_transient_source(self):
        env = harness_utils._harness_env(source="prosple")
        self.assertNotIn("BU_CDP_URL", env)

    def test_run_harness_uses_transient_browser_for_prosple(self):
        with mock.patch.object(
            harness_utils,
            "_run_harness_with_transient_browser",
            return_value=("out", "", 0),
        ) as transient, mock.patch.object(
            harness_utils,
            "_run_browser_harness",
            return_value=("", "", 0),
        ) as normal:
            out = harness_utils.run_harness("script", source="prosple")

        self.assertEqual(out, ("out", "", 0))
        transient.assert_called_once_with("script", 120, "prosple")
        normal.assert_not_called()

    def test_run_harness_uses_normal_browser_for_other_sources(self):
        with mock.patch.object(
            harness_utils,
            "_run_harness_with_transient_browser",
            return_value=("", "", 0),
        ) as transient, mock.patch.object(
            harness_utils,
            "_run_browser_harness",
            return_value=("out", "", 0),
        ) as normal:
            out = harness_utils.run_harness("script", source="seek")

        self.assertEqual(out, ("out", "", 0))
        transient.assert_not_called()
        normal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
