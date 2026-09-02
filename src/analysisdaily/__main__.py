"""python -m analysisdaily 入口：等价于 CLI。"""
import sys

from .orchestration.cli import main

if __name__ == "__main__":
    sys.exit(main())
