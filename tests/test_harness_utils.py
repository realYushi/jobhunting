import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib import harness_utils


class HarnessUtilsTests(unittest.TestCase):
    def test_harness_env_uses_dedicated_cdp_url_when_ready(self):
        with mock.patch.object(harness_utils, "_ensure_dedicated_browser", return_value="http://127.0.0.1:9333"):
            env = harness_utils._harness_env()
        self.assertEqual(env["BU_CDP_URL"], "http://127.0.0.1:9333")
        self.assertEqual(env["BU_NAME"], os.environ.get("JOBHUNTING_BROWSER_NAME", "jobhunting"))

    def test_harness_env_respects_explicit_browser_harness_override(self):
        with mock.patch.dict(os.environ, {"BU_CDP_URL": "http://127.0.0.1:9444"}, clear=False):
            env = harness_utils._harness_env()
        self.assertEqual(env["BU_CDP_URL"], "http://127.0.0.1:9444")

    def test_ensure_dedicated_browser_launches_headless_chrome(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d) / "profile"
            with mock.patch.object(harness_utils, "_DEFAULT_PROFILE_DIR", profile_dir), \
                 mock.patch.object(harness_utils, "_DEFAULT_CDP_URL", "http://127.0.0.1:9333"), \
                 mock.patch.object(harness_utils, "_find_chrome_binary", return_value="/chrome"), \
                 mock.patch.object(harness_utils, "_cdp_ready", side_effect=[False, True]), \
                 mock.patch.object(harness_utils.subprocess, "Popen") as popen:
                url = harness_utils._ensure_dedicated_browser()

        self.assertEqual(url, "http://127.0.0.1:9333")
        argv = popen.call_args.args[0]
        self.assertIn("--headless=new", argv)
        self.assertIn("--remote-debugging-port=9333", argv)
        self.assertTrue(any(str(profile_dir) in arg for arg in argv))


if __name__ == "__main__":
    unittest.main()
