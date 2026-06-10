import sys
import unittest
from pathlib import Path

from lib import jd_fetch
from lib.scorer import JobScore


class JdFetchParallelismTests(unittest.TestCase):
    def test_parallelism_is_serialized(self):
        self.assertEqual(jd_fetch.JD_FETCH_PARALLELISM, 1)

    def test_fetch_uses_single_worker_by_default(self):
        items = [
            JobScore(
                job_id="1",
                source="seek",
                title="Role",
                company="Acme",
                url="https://example.com/job/1",
                score=0,
                reason="",
            )
        ]

        original_executor = jd_fetch.ThreadPoolExecutor
        original_fetch = jd_fetch._fetch_full_jd
        calls = {}

        class FakeFuture:
            def __init__(self, value):
                self._value = value

            def result(self):
                return self._value

        class FakeExecutor:
            def __init__(self, max_workers):
                calls["max_workers"] = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, url, runner=None):
                calls.setdefault("urls", []).append(url)
                return FakeFuture(fn(url))

        try:
            jd_fetch.ThreadPoolExecutor = FakeExecutor
            jd_fetch._fetch_full_jd = lambda url: f"JD for {url}"
            out = jd_fetch._fetch_jds_parallel(items)
        finally:
            jd_fetch.ThreadPoolExecutor = original_executor
            jd_fetch._fetch_full_jd = original_fetch

        self.assertEqual(calls["max_workers"], 1)
        self.assertEqual(calls["urls"], ["https://example.com/job/1"])
        self.assertEqual(out["https://example.com/job/1"], "JD for https://example.com/job/1")


if __name__ == "__main__":
    unittest.main()
