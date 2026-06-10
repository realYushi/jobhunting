"""Tests for load_script tab lifecycle injection in harness_utils."""

import unittest

from lib import harness_utils


class LoadScriptTabLifecycleTests(unittest.TestCase):
    def test_list_script_contains_injected_tab_open(self):
        """load_script wraps a list script with new_tab using the url param."""
        script = harness_utils.load_script("seek-list", url="https://x", page=0)
        self.assertIn("new_tab('https://x')", script)

    def test_list_script_contains_injected_close_target(self):
        """load_script appends a closeTarget block for list scripts."""
        script = harness_utils.load_script("seek-list", url="https://x", page=0)
        self.assertIn("closeTarget", script)
        self.assertIn("_bh_tab", script)

    def test_list_script_injected_tab_comes_before_body(self):
        """The injected new_tab call must precede the script body."""
        script = harness_utils.load_script("seek-list", url="https://x", page=0)
        tab_pos = script.index("new_tab('https://x')")
        wait_pos = script.index("wait(2)")
        self.assertLess(tab_pos, wait_pos)

    def test_jd_fetch_does_not_get_injected_tab(self):
        """jd-fetch is not a list script and must not receive the tab wrapper."""
        script = harness_utils.load_script(
            "jd-fetch", url="https://example.com/job/1", pre_extract=""
        )
        # The injected wrapper uses _bh_tab; jd-fetch uses _tab_id on its own —
        # but after this refactor jd-fetch itself still owns its own lifecycle.
        # The key assertion: load_script must NOT inject a second new_tab wrapper.
        self.assertNotIn("_bh_tab", script)
        # And the injected prefix pattern must not appear.
        self.assertNotIn("new_tab('https://example.com/job/1')", script)


if __name__ == "__main__":
    unittest.main()
