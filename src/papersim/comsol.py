from __future__ import annotations

from dataclasses import dataclass, replace
import csv
import json
from pathlib import Path
import re
import shlex
import sys
import tarfile
import tempfile
import time
from typing import Any, Mapping

from .contracts import ContractError, TranslationGap, UnsupportedModel
from .store import read_json, sha256


class ComsolRemoteError(ContractError):
    pass


@dataclass(frozen=True)
class ComsolConfig:
    host: str
    port: int
    user: str
    instance_selection: str
    environment_script: str
    instance_id: str = ""
    identity_file: str = ""
    comsol_executable: str = "comsol"
    solver_version: str = "6.4"
    partition: str = "cpu"
    cpus: int = 8
    memory: str = "16G"
    remote_case_root: str = "~/papersim_cases"
    host_key_policy: str = "strict"

    @classmethod
    def load(cls, path: str | Path) -> "ComsolConfig":
        source = Path(path).expanduser()
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ComsolRemoteError(f"invalid COMSOL remote config {source}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ComsolRemoteError("COMSOL remote config must be a JSON object")
        ssh = raw.get("ssh")
        remote = raw.get("remote")
        if not isinstance(ssh, dict) or not isinstance(remote, dict):
            raise ComsolRemoteError("config requires ssh and remote objects")
        values = {
            "host": str(ssh.get("host") or "").strip(),
            "port": int(ssh.get("port") or 22),
            "user": str(ssh.get("user") or "").strip(),
            "instance_selection": str(ssh.get("instance_selection") or "").strip(),
            "instance_id": str(ssh.get("instance_id") or "").strip(),
            "identity_file": str(ssh.get("identity_file") or "").strip(),
            "environment_script": str(remote.get("environment_script") or "").strip(),
            "comsol_executable": str(remote.get("comsol_executable") or "comsol").strip(),
            "solver_version": str(remote.get("solver_version") or "6.4").strip(),
            "partition": str(remote.get("partition") or "cpu").strip(),
            "cpus": int(remote.get("cpus") or 8),
            "memory": str(remote.get("memory") or "16G").strip(),
            "remote_case_root": str(remote.get("remote_case_root") or "~/papersim_cases").strip(),
            "host_key_policy": str(ssh.get("host_key_policy") or "strict").strip(),
        }
        missing = [name for name, value in values.items() if name not in {"instance_id", "identity_file"} and not value]
        if missing:
            raise ComsolRemoteError(f"missing COMSOL remote config fields: {', '.join(missing)}")
        if not 1 <= values["port"] <= 65535:
            raise ComsolRemoteError("SSH port must be between 1 and 65535")
        if values["cpus"] < 1:
            raise ComsolRemoteError("COMSOL cpus must be positive")
        return cls(**values)


@dataclass(frozen=True)
class RemoteResult:
    command: str
    returncode: int
    output: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "returncode": self.returncode, "output": self.output}


def _load_pexpect():
    try:
        import pexpect
    except ImportError as exc:
        raise ComsolRemoteError("COMSOL remote agent requires pexpect>=4.8") from exc
    return pexpect


def _remote_path(value: str) -> str:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise ComsolRemoteError("invalid remote path")
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    return shlex.quote(value)


def _redact(value: str, secret: str) -> str:
    return value.replace(secret, "<redacted>") if secret else value


def _diagnostic(value: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value).strip()
    return cleaned[-500:] if cleaned else "no remote diagnostic"


class ComsolRemoteAgent:
    """Password-authenticated SSH/SCP gateway client.

    The password is read only from an external mode-0600 file. It is never
    stored in the profile, an artifact, a command line, or a log message.
    """

    def __init__(self, config: ComsolConfig, password_file: str | Path) -> None:
        self.config = config
        self.password_file = Path(password_file).expanduser()

    def probe(self) -> RemoteResult:
        command = (
            f"source {_remote_path(self.config.environment_script)} && "
            f"hostname && whoami && {_remote_path(self.config.comsol_executable)} -version 2>&1 | head -5 && "
            "command -v sbatch && sinfo -h -o '%P %a %D %T' | head -10"
        )
        return self.run(command, timeout=120)

    def run(self, command: str, *, timeout: int = 60) -> RemoteResult:
        pexpect = _load_pexpect()
        password = self._read_password()
        ssh_options = ["-tt", "-p", str(self.config.port), "-o", f"User={self._login_user()}"]
        if self.config.host_key_policy == "strict":
            ssh_options += ["-o", "StrictHostKeyChecking=yes"]
        elif self.config.host_key_policy == "accept-new":
            ssh_options += ["-o", "StrictHostKeyChecking=accept-new"]
        else:
            raise ComsolRemoteError("host_key_policy must be strict or accept-new")
        ssh_options += self._auth_options()
        ssh_options.append(f"{self._login_user()}@{self.config.host}")
        child = pexpect.spawn("ssh", ssh_options, encoding="utf-8", timeout=timeout)
        chunks: list[str] = []
        try:
            matched = child.expect([r"(?i)password[^:]*:", r"密码[^:：]*[:：]", pexpect.EOF, pexpect.TIMEOUT])
            chunks.append(_redact(child.before or "", password))
            if matched >= 2:
                raise ComsolRemoteError("SSH password or 2FA prompt was not reached")
            child.setecho(False)
            child.send(password + "\r")
            if "Key authentication required" in "".join(chunks):
                raise ComsolRemoteError(
                    "remote gateway requires SSH public-key authentication in addition to the password; "
                    "configure ssh.identity_file and register the corresponding public key"
                )
            if not self.config.instance_id:
                selected = child.expect([r"认证成功[^\r\n]*实例", r"(?i)select[^\r\n]*instance", pexpect.EOF, pexpect.TIMEOUT])
                chunks.append(child.before or "")
                if selected >= 2:
                    raise ComsolRemoteError("SSH gateway instance menu was not reached")
                child.send(self.config.instance_selection + "\r")
            entered = child.expect(
                [
                    r"(?m)[^\r\n]*[#$] ?$",
                    r"(?i)password[^:]*:",
                    r"密码[^:：]*[:：]",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                ],
                timeout=timeout,
            )
            chunks.append(_redact(child.before or "", password))
            if entered in {1, 2}:
                raise ComsolRemoteError(
                    "PEM key was accepted, but the keyboard-interactive 2FA password was rejected; "
                    "update the password file with the current remote gateway 2FA password"
                )
            if entered != 0:
                diagnostic = _diagnostic(chunks[-1] if chunks else "")
                if "Key authentication required" in diagnostic or "Invalid key" in diagnostic:
                    raise ComsolRemoteError(
                        "remote gateway rejected password-only authentication and now requires a registered SSH public key; "
                        "use an existing provider-issued identity or ask remote gateway to restore password-only access"
                    )
                raise ComsolRemoteError(f"selected instance did not produce a remote shell: {diagnostic}")
            child.send("stty -echo\r")
            if child.expect([r"(?m)[^\r\n]*[#$] ?$", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout) != 0:
                raise ComsolRemoteError("could not disable remote command echo")
            import uuid

            marker = f"__PAPERSIM_DONE_{uuid.uuid4().hex}__"
            wrapped = f"{command}; papersim_rc=$?; printf '\\n{marker}:%s\\n' \"$papersim_rc\""
            child.send(wrapped + "\r")
            finished = child.expect([rf"{re.escape(marker)}:(\d+)\r?\n", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
            chunks.append(child.before or "")
            if finished != 0 or child.match is None:
                raise ComsolRemoteError(f"remote command did not return a completion marker: {_diagnostic(''.join(chunks))}")
            returncode = int(child.match.group(1))
            child.send("exit\r")
            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=10)
            return RemoteResult(command=command, returncode=returncode, output="".join(chunks).strip())
        finally:
            child.close(force=True)

    def shell(self) -> RemoteResult:
        """Open an interactive remote shell using the stored password automatically."""
        pexpect = _load_pexpect()
        password = self._read_password()
        ssh_options = ["-tt", "-p", str(self.config.port), "-o", f"User={self._login_user()}"]
        if self.config.host_key_policy == "strict":
            ssh_options += ["-o", "StrictHostKeyChecking=yes"]
        elif self.config.host_key_policy == "accept-new":
            ssh_options += ["-o", "StrictHostKeyChecking=accept-new"]
        else:
            raise ComsolRemoteError("host_key_policy must be strict or accept-new")
        ssh_options += self._auth_options()
        ssh_options.append(f"{self._login_user()}@{self.config.host}")
        child = pexpect.spawn("ssh", ssh_options, encoding="utf-8", timeout=60)
        chunks: list[str] = []
        try:
            first = child.expect(
                [
                    r"(?i)password[^:]*:",
                    r"密码[^:：]*[:：]",
                    r"(?m)[^\r\n]*[#$] ?$",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                ]
            )
            chunks.append(_redact(child.before or "", password))
            if first in {0, 1}:
                child.setecho(False)
                child.send(password + "\r")
            elif first >= 3:
                raise ComsolRemoteError(f"SSH interactive login failed: {_diagnostic(chunks[-1])}")

            if not self.config.instance_id:
                selected = child.expect(
                    [
                        r"认证成功[^\r\n]*实例",
                        r"(?i)select[^\r\n]*instance",
                        r"(?m)[^\r\n]*[#$] ?$",
                        r"(?i)password[^:]*:",
                        pexpect.EOF,
                        pexpect.TIMEOUT,
                    ],
                    timeout=60,
                )
                chunks.append(_redact(child.before or "", password))
                if selected in {0, 1}:
                    child.send(self.config.instance_selection + "\r")
                elif selected >= 3:
                    diagnostic = _diagnostic(chunks[-1])
                    if "Key authentication required" in diagnostic or "Invalid key" in diagnostic:
                        raise ComsolRemoteError(
                            "remote gateway rejected password-only authentication and now requires a registered SSH public key; "
                            "use an existing provider-issued identity or ask remote gateway to restore password-only access"
                        )
                    raise ComsolRemoteError(f"remote gateway instance menu was not reached: {diagnostic}")

            entered = child.expect(
                [
                    r"(?m)[^\r\n]*[#$] ?$",
                    r"(?i)password[^:]*:",
                    r"密码[^:：]*[:：]",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                ],
                timeout=60,
            )
            chunks.append(_redact(child.before or "", password))
            if entered in {1, 2}:
                raise ComsolRemoteError(
                    "PEM key was accepted, but the keyboard-interactive 2FA password was rejected; "
                    "update the password file with the current remote gateway 2FA password"
                )
            if entered != 0:
                diagnostic = _diagnostic(chunks[-1])
                if "Key authentication required" in diagnostic or "Invalid key" in diagnostic:
                    raise ComsolRemoteError(
                        "remote gateway rejected password-only authentication and now requires a registered SSH public key; "
                        "use an existing provider-issued identity or ask remote gateway to restore password-only access"
                    )
                raise ComsolRemoteError(f"interactive shell was not reached: {diagnostic}")
            print("Connected to remote gateway. Press Ctrl-] to leave the interactive session.", file=sys.stderr)
            child.interact(escape_character="\x1d")
            return RemoteResult(command="ssh-shell", returncode=0, output="interactive session closed")
        finally:
            child.close(force=True)

    def upload(self, local_path: str | Path, remote_path: str, *, timeout: int = 1800) -> RemoteResult:
        return self._transfer(
            [
                "-P",
                str(self.config.port),
                "-o",
                f"User={self._login_user()}",
                "-o",
                "StrictHostKeyChecking=yes" if self.config.host_key_policy == "strict" else "StrictHostKeyChecking=accept-new",
                *self._auth_options(),
                "--",
                str(local_path),
                f"{self.config.host}:{remote_path}",
            ],
            timeout=timeout,
        )

    def download(self, remote_path: str, local_path: str | Path, *, timeout: int = 1800) -> RemoteResult:
        return self._transfer(
            [
                "-P",
                str(self.config.port),
                "-o",
                f"User={self._login_user()}",
                "-o",
                "StrictHostKeyChecking=yes" if self.config.host_key_policy == "strict" else "StrictHostKeyChecking=accept-new",
                *self._auth_options(),
                "--",
                f"{self.config.host}:{remote_path}",
                str(local_path),
            ],
            timeout=timeout,
        )

    def _transfer(self, args: list[str], *, timeout: int) -> RemoteResult:
        pexpect = _load_pexpect()
        password = self._read_password()
        child = pexpect.spawn("scp", args, encoding="utf-8", timeout=timeout)
        chunks: list[str] = []
        try:
            matched = child.expect([r"(?i)password[^:]*:", r"密码[^:：]*[:：]", pexpect.EOF, pexpect.TIMEOUT])
            chunks.append(_redact(child.before or "", password))
            if matched >= 2:
                raise ComsolRemoteError(f"SCP password or 2FA prompt was not reached: {_diagnostic(_redact(child.before or '', password))}")
            child.setecho(False)
            child.send(password + "\r")
            last_percent: int | None = None
            while True:
                quiet_timeout = min(timeout, 30) if last_percent is not None else min(timeout, 60)
                completed = child.expect(
                    [
                        r"认证成功[^\r\n]*实例",
                        r"(?i)select[^\r\n]*instance",
                        r"([0-9]{1,3})%",
                        r"(?m)[^\r\n]*[#$] ?$",
                        r"(?i)password[^:]*:",
                        r"密码[^:：]*[:：]",
                        pexpect.EOF,
                        pexpect.TIMEOUT,
                    ],
                    timeout=quiet_timeout,
                )
                chunks.append(_redact(child.before or "", password))
                if completed in {0, 1}:
                    child.send(self.config.instance_selection + "\r")
                    continue
                if completed in {4, 5}:
                    diagnostic = "".join(chunks)
                    if "Invalid key" in diagnostic or "Key authentication required" in diagnostic:
                        raise ComsolRemoteError(
                            "remote gateway requires the provider-issued PEM followed by keyboard-interactive 2FA; "
                            "update the 2FA password file or verify the identity file"
                        )
                    raise ComsolRemoteError(f"SCP gateway authentication failed: {_diagnostic(diagnostic)}")
                if completed == 2:
                    last_percent = int(child.match.group(1))
                    if not 0 <= last_percent <= 100:
                        raise ComsolRemoteError(f"invalid SCP progress marker: {last_percent}%")
                    continue
                if completed == 3:
                    child.send("exit\r")
                    child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=10)
                    return RemoteResult(command="scp", returncode=0, output="".join(chunks).strip())
                if completed == 6:
                    returncode = child.exitstatus if child.exitstatus is not None else 1
                    return RemoteResult(command="scp", returncode=returncode, output="".join(chunks).strip())
                if last_percent == 100:
                    return RemoteResult(command="scp", returncode=0, output="".join(chunks).strip())
                if last_percent is None:
                    raise ComsolRemoteError("SCP transfer timed out before reporting progress")
                raise ComsolRemoteError(f"SCP transfer stalled at {last_percent}%")
        finally:
            child.close(force=True)

    def _auth_options(self) -> list[str]:
        if self.config.identity_file:
            identity = Path(self.config.identity_file).expanduser()
            if not identity.is_file():
                raise ComsolRemoteError(f"SSH identity file does not exist: {identity}")
            return [
                "-i",
                str(identity),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "PreferredAuthentications=publickey,keyboard-interactive",
            ]
        return [
            "-o",
            "PubkeyAuthentication=no",
            "-o",
            "PreferredAuthentications=password,keyboard-interactive",
        ]

    def _login_user(self) -> str:
        return f"{self.config.user}::{self.config.instance_id}" if self.config.instance_id else self.config.user

    def _read_password(self) -> str:
        try:
            mode = self.password_file.stat().st_mode & 0o777
            if mode & 0o077:
                raise ComsolRemoteError("password file must not be accessible by group or others")
            password = self.password_file.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise ComsolRemoteError(f"cannot read password file: {exc}") from exc
        if not password:
            raise ComsolRemoteError("password file is empty")
        return password


class ComsolBackend:
    adapter_name = "comsol"
    adapter_version = "1.0"

    def __init__(
        self,
        *,
        config: str | Path | None = None,
        password_file: str | Path | None = None,
        remote_root: str | None = None,
        suite: str = "full",
    ) -> None:
        if config is None:
            raise ComsolRemoteError("COMSOL backend requires a connection profile")
        if password_file is None:
            raise ComsolRemoteError("COMSOL backend requires an external password file")
        self.config = ComsolConfig.load(config)
        self.password_file = Path(password_file).expanduser()
        self.remote_root = remote_root
        self.suite = suite
        self._runs: dict[str, dict[str, Any]] = {}

    def _spec(self, model: Any) -> dict[str, Any]:
        ref = model.data["model_spec"]
        path = Path(str(ref["path"]))
        if not path.is_absolute():
            path = Path(model.path).parent.parent / "artifacts" / path.name
        return read_json(path)

    def validate(self, model: Any) -> None:
        spec = self._spec(model)
        solver = spec.get("solver")
        if not isinstance(solver, dict) or solver.get("backend") != "comsol":
            raise UnsupportedModel("COMSOL backend requires model.spec.json.solver.backend=comsol")
        if not isinstance(solver.get("entrypoint"), str) or not solver["entrypoint"].strip():
            raise TranslationGap("COMSOL model spec requires solver.entrypoint")
        suites = solver.get("suite")
        if not isinstance(suites, dict) or self.suite not in suites:
            raise TranslationGap(f"COMSOL model spec does not define solver suite '{self.suite}'")
        if not isinstance(suites[self.suite], list) or not suites[self.suite]:
            raise TranslationGap(f"COMSOL suite '{self.suite}' is empty")

    def build(self, model: Any, run_id: str) -> dict[str, Any]:
        spec = self._spec(model)
        solver = spec["solver"]
        staging_value = solver.get("staging_dir")
        staging: Path | None = None
        if isinstance(staging_value, str):
            candidate = Path(staging_value).expanduser()
            if candidate.is_dir():
                staging = candidate.resolve()
            elif candidate.parts == ("solver",) and model.data.get("bundle"):
                bundle_ref = model.data["bundle"]
                bundle_path = Path(str(bundle_ref["path"]))
                if not bundle_path.is_absolute():
                    bundle_path = Path(model.path).parent.parent / "artifacts" / bundle_path.name
                extract_root = Path(tempfile.mkdtemp(prefix=f"papersim_{run_id}_model_", dir=tempfile.gettempdir())).resolve()
                with tarfile.open(bundle_path, "r:gz") as handle:
                    for member in handle.getmembers():
                        target = (extract_root / member.name).resolve()
                        if extract_root != target and extract_root not in target.parents:
                            raise TranslationGap(f"model bundle contains an unsafe path: {member.name}")
                    handle.extractall(extract_root)
                staging = extract_root / "solver"
        if staging is None or not staging.is_dir():
            raise TranslationGap("COMSOL requires a bundled solver directory or a valid solver.staging_dir")
        archive = Path(tempfile.gettempdir()) / f"papersim_{run_id}_model.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(staging, arcname="solver")
        return {"archive": str(archive), "suite": self.suite, "entrypoint": solver["entrypoint"]}

    def submit(self, model: Any, run_id: str) -> dict[str, Any]:
        spec = self._spec(model)
        solver = spec["solver"]
        run_root = self.remote_root or f"{self.config.remote_case_root}/{model.data['case_id']}/{run_id}"
        agent = ComsolRemoteAgent(self.config, self.password_file)
        remote_input = f"{run_root}/input"
        remote_suite = f"{run_root}/suite"
        result = agent.run(f"mkdir -p {_remote_path(remote_input)} {_remote_path(remote_suite)}", timeout=120)
        if not result.ok:
            raise ComsolRemoteError(f"cannot create remote run root: {result.output}")
        build_result = self.build(model, run_id)
        upload = agent.upload(Path(build_result["archive"]), f"{remote_input}/model.tar.gz", timeout=1800)
        if not upload.ok:
            raise ComsolRemoteError(f"model upload failed: {upload.output}")
        unpack = agent.run(f"cd {_remote_path(remote_input)} && rm -rf solver && tar -xzf model.tar.gz", timeout=600)
        if not unpack.ok:
            raise ComsolRemoteError(f"model unpack failed: {unpack.output}")
        case_specs = [str(item) for item in solver["suite"][self.suite]]
        cases = [Path(item).stem for item in case_specs]
        quoted_cases = " ".join(_remote_path(item) for item in case_specs)
        entrypoint = f"{remote_input}/solver/{solver['entrypoint']}"
        command = (
            f"source {_remote_path(self.config.environment_script)} && "
            f"cd {_remote_path(remote_input)} && "
            f"bash {_remote_path(entrypoint)} {_remote_path(remote_suite)} {quoted_cases}"
        )
        submitted = agent.run(command, timeout=600)
        if not submitted.ok:
            raise ComsolRemoteError(f"COMSOL submission failed: {submitted.output}")
        jobs: dict[str, str] = {}
        for prefix, job_id in re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)=(\d+)\s*$", submitted.output):
            jobs[prefix] = job_id
        if set(jobs) != set(cases):
            raise ComsolRemoteError(f"submitted jobs do not match suite: expected={cases}, got={sorted(jobs)}")
        data = {
            "status": "submitted",
            "exit_code": None,
            "solver": self.adapter_name,
            "solver_version": self.config.solver_version,
            "environment": {
                "host": self.config.host,
                "instance_id": self.config.instance_id,
                "environment_script": self.config.environment_script,
                "comsol_executable": self.config.comsol_executable,
                "partition": self.config.partition,
            },
            "remote": {"root": run_root, "jobs": jobs},
            "jobs": jobs,
            "metrics": {},
        }
        data["artifact_policy"] = dict(solver.get("artifact_policy") or {})
        self._runs[run_id] = data
        return data

    def status(self, run_id: str) -> dict[str, Any]:
        data = self._runs.get(run_id)
        if data is None:
            return {"status": "unknown", "exit_code": None}
        agent = ComsolRemoteAgent(self.config, self.password_file)
        jobs = data.get("jobs", {})
        states: dict[str, Any] = {}
        terminal = True
        for name, job_id in jobs.items():
            result = agent.run(f"sacct -j {shlex.quote(str(job_id))} --format=JobID,State,ExitCode,Elapsed -n -P | awk 'NF {{print; exit}}'", timeout=120)
            line = result.output.strip().splitlines()[-1] if result.output.strip() else ""
            fields = line.split("|")
            if len(fields) < 4:
                states[name] = {"job_id": job_id, "state": "UNKNOWN", "raw": result.output}
                terminal = False
            else:
                states[name] = {"job_id": job_id, "state": fields[1], "exit_code": fields[2], "elapsed": fields[3]}
                if fields[1] not in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}:
                    terminal = False
        if terminal:
            failed = any(item.get("state") != "COMPLETED" or str(item.get("exit_code")) != "0:0" for item in states.values())
            data["status"] = "failed" if failed else "complete"
            data["exit_code"] = 1 if failed else 0
            data["job_status"] = states
        else:
            data["status"] = "running"
            data["exit_code"] = None
            data["job_status"] = states
        self._runs[run_id] = data
        return dict(data)

    def collect(self, run_id: str, workdir: Any = None) -> dict[str, Any]:
        data = self._runs.get(run_id)
        if data is None or data.get("status") != "complete":
            raise ComsolRemoteError(f"cannot collect incomplete COMSOL run: {run_id}")
        agent = ComsolRemoteAgent(self.config, self.password_file)
        remote_root = str(data["remote"]["root"])
        remote_archive = f"{remote_root}/results.tar.gz"
        result = agent.run(
            f"cd {_remote_path(remote_root)} && tar -czf results.tar.gz -C suite . && sha256sum results.tar.gz",
            timeout=1800,
        )
        if not result.ok:
            raise ComsolRemoteError(f"result packing failed: {result.output}")
        local_archive = Path(tempfile.gettempdir()) / f"papersim_{run_id}_results.tar.gz"
        remote_hashes = re.findall(r"\b[a-f0-9]{64}\b", result.output)
        if not remote_hashes:
            raise ComsolRemoteError("remote result archive did not return a SHA-256 hash")
        download = agent.download(remote_archive, local_archive, timeout=3600)
        if not download.ok and not (local_archive.is_file() and sha256(local_archive) == remote_hashes[-1]):
            raise ComsolRemoteError(f"result download failed: {download.output}")
        if sha256(local_archive) != remote_hashes[-1]:
            raise ComsolRemoteError("downloaded result archive SHA-256 does not match the remote archive")
        extract_root = Path(tempfile.mkdtemp(prefix=f"papersim_{run_id}_", dir=tempfile.gettempdir())).resolve()
        with tarfile.open(local_archive, "r:gz") as handle:
            for member in handle.getmembers():
                target = (extract_root / member.name).resolve()
                if extract_root != target and extract_root not in target.parents:
                    raise ComsolRemoteError(f"result archive contains an unsafe path: {member.name}")
            handle.extractall(extract_root)
        artifacts = [str(path) for path in sorted(extract_root.rglob("*")) if path.is_file()]
        required_artifacts = [item for item in artifacts if Path(item).suffix.lower() in {".mph", ".csv"}]
        if not required_artifacts or any(Path(item).stat().st_size == 0 for item in required_artifacts):
            raise ComsolRemoteError("COMSOL result archive is missing a nonempty MPH or CSV artifact")
        metrics = _collect_metrics(extract_root, data.get("metrics", {}))
        logs = _collect_logs(extract_root)
        for log_text in logs:
            if re.search(r"(?i)\b(error|exception|filenotfound|license error|failed)\b", log_text):
                raise ComsolRemoteError("COMSOL log contains a fatal diagnostic")

        policy = data.get("artifact_policy") or {}
        local_patterns = [str(item) for item in policy.get("local_globs", [])]
        authoritative_pattern = policy.get("authoritative_glob")
        local_paths: list[Path] = []
        for item in artifacts:
            path = Path(item)
            relative = path.relative_to(extract_root).as_posix()
            if not local_patterns or _matches_globs(relative, local_patterns) or (
                authoritative_pattern and _matches_globs(relative, [str(authoritative_pattern)])
            ):
                local_paths.append(path)
        if authoritative_pattern:
            matches = [
                path
                for path in local_paths
                if _matches_globs(path.relative_to(extract_root).as_posix(), [str(authoritative_pattern)])
            ]
            if len(matches) != 1:
                raise ComsolRemoteError(
                    f"artifact policy requires exactly one authoritative match, got {len(matches)}"
                )
        local_set = {path.resolve() for path in local_paths}
        remote_artifacts = [
            _remote_artifact_record(path, extract_root, str(remote_root))
            for path in map(Path, artifacts)
            if path.resolve() not in local_set
        ]
        return {
            "status": "complete",
            "exit_code": 0,
            "solver": self.adapter_name,
            "solver_version": self.config.solver_version,
            "environment": data.get("environment", {}),
            "metrics": metrics,
            "remote": data.get("remote", {}),
            "logs": ["COMSOL jobs completed; result archive SHA-256 matched remote hash"] + logs,
            "artifacts": [str(path) for path in local_paths],
            "remote_artifacts": remote_artifacts,
        }



def _matches_globs(relative: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatchcase

    return any(fnmatchcase(relative, pattern) for pattern in patterns)


def _remote_artifact_record(path: Path, root: Path, remote_root: str) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    suffix = path.suffix.lower()
    media_type = {
        ".mph": "application/vnd.comsol.mph",
        ".csv": "text/csv",
        ".log": "text/plain",
        ".out": "text/plain",
        ".err": "text/plain",
        ".sha256": "text/plain",
    }.get(suffix, "application/octet-stream")
    return {
        "name": relative,
        "sha256": sha256(path),
        "size": path.stat().st_size,
        "media_type": media_type,
        "remote_path": f"{remote_root.rstrip('/')}/{relative}",
    }


def _collect_metrics(root: Path, fallback: Mapping[str, Any]) -> dict[str, Any]:
    for path in sorted(root.rglob("metrics.json")):
        try:
            value = read_json(path)
        except Exception:
            continue
        if isinstance(value, dict):
            return value
    metrics: dict[str, Any] = dict(fallback)
    for path in sorted(root.rglob("*.csv")):
        try:
            lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
            header_index = None
            for index, line in enumerate(lines):
                stripped = line.strip()
                candidate = stripped[1:].strip() if stripped.startswith("%") else stripped
                lower = candidate.lower()
                if "," not in candidate:
                    continue
                if lower.startswith(("time", "x,y")) or not lower.startswith(("model", "version", "date", "table", "dimension", "nodes", "expressions", "description", "length unit")):
                    if index + 1 < len(lines):
                        header_index = index
                        break
            if header_index is None:
                continue
            reader = csv.reader(lines[header_index:], skipinitialspace=True)
            header = next(reader, None)
            if not header:
                continue
            rows = [row for row in reader if row]
            if not rows:
                continue
            for column, value in zip(header, rows[-1]):
                clean_column = re.sub(r"\s*\([^)]*\)\s*$", "", str(column)).strip()
                try:
                    metrics[f"{path.stem}.{clean_column}"] = float(value)
                except (TypeError, ValueError):
                    continue
        except OSError:
            continue
    return metrics


def _collect_logs(root: Path) -> list[str]:
    logs: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".log", ".out", ".err", ".txt"}:
            try:
                logs.append(path.read_text(encoding="utf-8", errors="replace")[-20000:])
            except OSError:
                continue
    return logs


class ComsolSuiteRunner(ComsolBackend):
    """Backward-compatible name for hosts that previously injected a runner."""

    pass

ComsolRemoteConfig = ComsolConfig
