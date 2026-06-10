#!/usr/bin/env python3
"""Print application tracker status and missing local artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

from lib.paths import tracker_path  # noqa: E402
from lib.tracker import load_tracker, tracker_summary  # noqa: E402


def main() -> None:
    path = tracker_path()
    tracker = load_tracker(path)
    print(f"Tracker: {path}")
    print("\n".join(tracker_summary(tracker)))


if __name__ == "__main__":
    main()
