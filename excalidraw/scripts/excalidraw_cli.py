#!/usr/bin/env python3
"""独立启动器：可从任意目录以 `python excalidraw_cli.py ...` 调用 CLI。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from excalidraw.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
