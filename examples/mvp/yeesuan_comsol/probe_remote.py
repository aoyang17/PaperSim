#!/usr/bin/env python3
"""Probe the configured remote gateway COMSOL instance without exposing secrets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yeesuan_executor import YeesuanConfig, YeesuanExecutor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="~/.config/papersim/yeesuan_comsol.json")
    parser.add_argument("--password-file", default="~/.config/papersim/yeesuan_password")
    args = parser.parse_args()
    password_file = Path(args.password_file) if args.password_file else None
    agent = YeesuanExecutor(YeesuanConfig.load(Path(args.config)), password_file)
    result = agent.probe()
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
