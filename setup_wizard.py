#!/usr/bin/env python3
"""Standalone entry point — works before 'pip install -e .'"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from octobot.wizard import main

if __name__ == "__main__":
    main()
