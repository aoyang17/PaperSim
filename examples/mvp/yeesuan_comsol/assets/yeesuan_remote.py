#!/usr/bin/env python3
"""Non-interactive transport helper for the remote gateway COMSOL gateway."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path

DEFAULT_CONFIG = Path("~/.config/papersim/yeesuan_comsol.json").expanduser()
DEFAULT_PASSWORD = Path("~/.config/papersim/yeesuan_password").expanduser()


def _load_papersim():
    source = Path(os.environ.get("PAPERSIM_SRC") or Path(__file__).resolve().parents[4] / "src").expanduser()
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    example_dir = Path(__file__).resolve().parents[1]
    if str(example_dir) not in sys.path:
        sys.path.insert(0, str(example_dir))
    try:
        from yeesuan_executor import YeesuanConfig, YeesuanExecutor
    except ImportError as exc:
        raise SystemExit(
            "Cannot import the Yeesuan MVP executor. Set PAPERSIM_SRC or run from the example directory."
        ) from exc
    return YeesuanConfig, YeesuanExecutor


def _remote_path(value: str) -> str:
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    return shlex.quote(value)


def _mode(path: Path) -> str:
    return oct(path.stat().st_mode & 0o777)


def _check(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser()
    password_path = Path(args.password_file).expanduser()
    if not config_path.is_file():
        raise SystemExit(f"missing gateway config: {config_path}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    ssh = raw.get("ssh") or {}
    identity = Path(str(ssh.get("identity_file") or "")).expanduser() if ssh.get("identity_file") else None
    direct_identity = bool(str(ssh.get("instance_id") or "").strip() and identity and identity.is_file())
    result = {
        "config": str(config_path),
        "config_mode": _mode(config_path),
        "password_file": str(password_path),
        "password_mode": _mode(password_path) if password_path.is_file() else None,
        "identity_file": str(identity) if identity else None,
        "identity_mode": _mode(identity) if identity and identity.exists() else None,
        "identity_exists": bool(identity and identity.is_file()),
        "public_key_exists": bool(identity and Path(str(identity) + ".pub").is_file()),
        "public_key_fingerprint": None,
        "auth_mode": "publickey" if direct_identity else ("password+publickey" if identity else "password"),
        "instance_id": str(ssh.get("instance_id") or ""),
        "host": str(ssh.get("host") or ""),
        "port": int(ssh.get("port") or 0),
    }
    if not direct_identity and not password_path.is_file():
        raise SystemExit(f"missing password file: {password_path}")
    if password_path.is_file() and stat.S_IMODE(password_path.stat().st_mode) & 0o077:
        raise SystemExit(f"password file must be mode 0600: {password_path}")
    if identity and not identity.is_file():
        raise SystemExit(f"configured identity file does not exist: {identity}")
    if identity and stat.S_IMODE(identity.stat().st_mode) & 0o077:
        raise SystemExit(f"identity file must be mode 0600: {identity}")
    if identity and Path(str(identity) + ".pub").is_file():
        fingerprint = subprocess.run(
            ["ssh-keygen", "-lf", str(identity) + ".pub"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result["public_key_fingerprint"] = fingerprint
    _load_papersim()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _agent(args: argparse.Namespace):
    YeesuanConfig, YeesuanExecutor = _load_papersim()
    return YeesuanExecutor(
        YeesuanConfig.load(args.config),
        Path(args.password_file).expanduser(),
    )


def _run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    result = _agent(args).run(" ".join(command), timeout=args.timeout)
    if result.output:
        print(result.output)
    return result.returncode


def _probe(args: argparse.Namespace) -> int:
    result = _agent(args).probe()
    if result.output:
        print(result.output)
    return result.returncode


def _shell(args: argparse.Namespace) -> int:
    result = _agent(args).shell()
    return result.returncode


def _upload(args: argparse.Namespace) -> int:
    result = _agent(args).upload(args.local, args.remote, timeout=args.timeout)
    if result.output:
        print(result.output)
    return result.returncode


def _download(args: argparse.Namespace) -> int:
    result = _agent(args).download(args.remote, args.local, timeout=args.timeout)
    if result.output:
        print(result.output)
    return result.returncode


def _remote_command(args: argparse.Namespace) -> int:
    config, _ = _load_papersim()
    loaded = config.load(args.config)
    if args.action == "mkdir":
        command = f"mkdir -p {_remote_path(args.path)}"
    elif args.action == "tail":
        command = f"tail -n {int(args.lines)} -- {_remote_path(args.path)}"
    elif args.action == "submit":
        project = _remote_path(args.project)
        script = _remote_path(args.script)
        command = (
            f"source {_remote_path(loaded.environment_script)} && "
            f"cd {project} && sbatch --parsable --export=ALL,PROJECT_ROOT={project} {script}"
        )
    elif args.action == "status":
        job = shlex.quote(str(args.job_id))
        command = (
            f"source {_remote_path(loaded.environment_script)} && "
            f"squeue -j {job} -o '%.18i %.9P %.24j %.8T %.10M %.6D %R' 2>/dev/null || true; "
            f"sacct -j {job} --format=JobID,JobName%24,Partition,State,ExitCode,Elapsed -n -P"
        )
    else:
        raise SystemExit(f"unsupported remote action: {args.action}")
    result = _agent(args).run(command, timeout=args.timeout)
    if result.output:
        print(result.output)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yeesuan_remote.py")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--password-file", default=str(DEFAULT_PASSWORD))
    parser.add_argument("--timeout", type=int, default=120)
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check")
    check.set_defaults(func=_check)

    probe = sub.add_parser("probe")
    probe.set_defaults(func=_probe)

    shell = sub.add_parser("shell")
    shell.set_defaults(func=_shell)

    run = sub.add_parser("run")
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=_run)

    upload = sub.add_parser("upload")
    upload.add_argument("local")
    upload.add_argument("remote")
    upload.set_defaults(func=_upload)

    download = sub.add_parser("download")
    download.add_argument("remote")
    download.add_argument("local")
    download.set_defaults(func=_download)

    for action in ("mkdir", "tail", "submit", "status"):
        item = sub.add_parser(action)
        item.set_defaults(func=_remote_command, action=action)
        if action == "mkdir":
            item.add_argument("path")
        elif action == "tail":
            item.add_argument("path")
            item.add_argument("--lines", type=int, default=120)
        elif action == "submit":
            item.add_argument("project")
            item.add_argument("script", nargs="?", default="slurm/comsol_job.slurm")
        elif action == "status":
            item.add_argument("job_id")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        if os.environ.get("YEESUAN_DEBUG"):
            raise
        print(f"yeesuan-comsol: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
