#!/usr/bin/env python3
"""Probe the configured remote gateway COMSOL instance without exposing secrets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from papersim.comsol import ComsolConfig, ComsolRemoteAgent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="~/.config/papersim/comsol_remote.json")
    parser.add_argument("--password-file", default="~/.config/papersim/comsol_password")
    args = parser.parse_args()
    agent = ComsolRemoteAgent(ComsolConfig.load(Path(args.config)), Path(args.password_file))
    result = agent.probe()
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
