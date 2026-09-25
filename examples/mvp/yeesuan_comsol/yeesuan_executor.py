from __future__ import annotations

from dataclasses import dataclass
import json
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from papersim.contracts import ContractError, RemoteResult


class YeesuanRemoteError(ContractError):
    """Raised when the Yeesuan MVP gateway adapter cannot complete an operation."""


@dataclass(frozen=True)
class YeesuanConfig:
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
    def load(cls, path: str | Path) -> "YeesuanConfig":
        source = Path(path).expanduser()
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise YeesuanRemoteError(f"invalid COMSOL remote config {source}: {exc}") from exc
        if not isinstance(raw, dict):
            raise YeesuanRemoteError("COMSOL remote config must be a JSON object")
        ssh = raw.get("ssh")
        remote = raw.get("remote")
        if not isinstance(ssh, dict) or not isinstance(remote, dict):
            raise YeesuanRemoteError("config requires ssh and remote objects")
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
            raise YeesuanRemoteError(f"missing COMSOL remote config fields: {', '.join(missing)}")
        if not 1 <= values["port"] <= 65535:
            raise YeesuanRemoteError("SSH port must be between 1 and 65535")
        if values["cpus"] < 1:
            raise YeesuanRemoteError("COMSOL cpus must be positive")
        return cls(**values)


def _load_pexpect():
    try:
        import pexpect
    except ImportError as exc:
        raise YeesuanRemoteError("COMSOL remote agent requires pexpect>=4.8") from exc
    return pexpect


def _remote_path(value: str) -> str:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise YeesuanRemoteError("invalid remote path")
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    return shlex.quote(value)


def _redact(value: str, secret: str) -> str:
    return value.replace(secret, "<redacted>") if secret else value


def _diagnostic(value: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value).strip()
    return cleaned[-500:] if cleaned else "no remote diagnostic"


class YeesuanExecutor:
    """Yeesuan-specific :class:`RemoteExecutor` MVP implementation.

    This class is intentionally outside the PaperSim package. It demonstrates
    one external solver transport; users can replace it without changing the
    solver protocol or COMSOL model/audit logic.
    """

    def __init__(self, config: YeesuanConfig, password_file: str | Path | None = None) -> None:
        self.config = config
        self.password_file = Path(password_file).expanduser() if password_file is not None else None

    def describe(self) -> Mapping[str, Any]:
        return {
            "executor": "yeesuan-comsol-mvp",
            "host": self.config.host,
            "user": self.config.user,
            "instance_id": self.config.instance_id,
            "environment_script": self.config.environment_script,
            "comsol_executable": self.config.comsol_executable,
            "solver_version": self.config.solver_version,
            "partition": self.config.partition,
        }

    def probe(self) -> RemoteResult:
        command = (
            f"hostname && whoami && {_remote_path(self.config.comsol_executable)} -version 2>&1 | head -5 && "
            "command -v sbatch && sinfo -h -o '%P %a %D %T' | head -10"
        )
        return self.run(command, timeout=120)

    def run(self, command: str, *, timeout: int = 60) -> RemoteResult:
        command = self._wrap_command(command)
        if self._uses_direct_identity():
            return self._run_direct(command, timeout=timeout)
        pexpect = _load_pexpect()
        password = self._read_password()
        ssh_options = ["-tt", "-p", str(self.config.port), "-o", f"User={self._login_user()}"]
        if self.config.host_key_policy == "strict":
            ssh_options += ["-o", "StrictHostKeyChecking=yes"]
        elif self.config.host_key_policy == "accept-new":
            ssh_options += ["-o", "StrictHostKeyChecking=accept-new"]
        else:
            raise YeesuanRemoteError("host_key_policy must be strict or accept-new")
        ssh_options += self._auth_options()
        ssh_options.append(f"{self._login_user()}@{self.config.host}")
        child = pexpect.spawn("ssh", ssh_options, encoding="utf-8", timeout=timeout)
        chunks: list[str] = []
        try:
            matched = child.expect([r"(?i)password[^:]*:", r"密码[^:：]*[:：]", pexpect.EOF, pexpect.TIMEOUT])
            chunks.append(_redact(child.before or "", password))
            if matched >= 2:
                raise YeesuanRemoteError("SSH password or 2FA prompt was not reached")
            child.setecho(False)
            child.send(password + "\r")
            if "Key authentication required" in "".join(chunks):
                raise YeesuanRemoteError(
                    "remote gateway requires SSH public-key authentication in addition to the password; "
                    "configure ssh.identity_file and register the corresponding public key"
                )
            if not self.config.instance_id:
                selected = child.expect([r"认证成功[^\r\n]*实例", r"(?i)select[^\r\n]*instance", pexpect.EOF, pexpect.TIMEOUT])
                chunks.append(child.before or "")
                if selected >= 2:
                    raise YeesuanRemoteError("SSH gateway instance menu was not reached")
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
                raise YeesuanRemoteError(
                    "PEM key was accepted, but the keyboard-interactive 2FA password was rejected; "
                    "update the password file with the current remote gateway 2FA password"
                )
            if entered != 0:
                diagnostic = _diagnostic(chunks[-1] if chunks else "")
                if "Key authentication required" in diagnostic or "Invalid key" in diagnostic:
                    raise YeesuanRemoteError(
                        "remote gateway rejected password-only authentication and now requires a registered SSH public key; "
                        "use an existing provider-issued identity or ask remote gateway to restore password-only access"
                    )
                raise YeesuanRemoteError(f"selected instance did not produce a remote shell: {diagnostic}")
            child.send("stty -echo\r")
            if child.expect([r"(?m)[^\r\n]*[#$] ?$", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout) != 0:
                raise YeesuanRemoteError("could not disable remote command echo")
            import uuid

            marker = f"__PAPERSIM_DONE_{uuid.uuid4().hex}__"
            wrapped = f"{command}; papersim_rc=$?; printf '\\n{marker}:%s\\n' \"$papersim_rc\""
            child.send(wrapped + "\r")
            finished = child.expect([rf"{re.escape(marker)}:(\d+)\r?\n", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
            chunks.append(child.before or "")
            if finished != 0 or child.match is None:
                raise YeesuanRemoteError(f"remote command did not return a completion marker: {_diagnostic(''.join(chunks))}")
            returncode = int(child.match.group(1))
            child.send("exit\r")
            child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=10)
            return RemoteResult(command=command, returncode=returncode, output="".join(chunks).strip())
        finally:
            child.close(force=True)

    def _run_direct(self, command: str, *, timeout: int) -> RemoteResult:
        ssh_options = self._ssh_options(tty=False)
        ssh_options.append(f"{self._login_user()}@{self.config.host}")
        ssh_options.append(command)
        try:
            completed = subprocess.run(
                ["ssh", *ssh_options],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise YeesuanRemoteError(f"remote command timed out after {timeout}s") from exc
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
        )
        return RemoteResult(command=command, returncode=completed.returncode, output=output)

    def shell(self) -> RemoteResult:
        """Open an interactive remote shell using the stored password automatically."""
        if self._uses_direct_identity():
            pexpect = _load_pexpect()
            ssh_options = self._ssh_options(tty=True)
            ssh_options.append(f"{self._login_user()}@{self.config.host}")
            child = pexpect.spawn("ssh", ssh_options, encoding="utf-8", timeout=60)
            try:
                print("Connected with direct PEM authentication. Press Ctrl-] to leave the interactive session.", file=sys.stderr)
                child.interact(escape_character="\x1d")
            finally:
                child.close(force=True)
            return RemoteResult(command="ssh-shell", returncode=0, output="interactive session closed")
        pexpect = _load_pexpect()
        password = self._read_password()
        ssh_options = ["-tt", "-p", str(self.config.port), "-o", f"User={self._login_user()}"]
        if self.config.host_key_policy == "strict":
            ssh_options += ["-o", "StrictHostKeyChecking=yes"]
        elif self.config.host_key_policy == "accept-new":
            ssh_options += ["-o", "StrictHostKeyChecking=accept-new"]
        else:
            raise YeesuanRemoteError("host_key_policy must be strict or accept-new")
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
                raise YeesuanRemoteError(f"SSH interactive login failed: {_diagnostic(chunks[-1])}")

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
                        raise YeesuanRemoteError(
                            "remote gateway rejected password-only authentication and now requires a registered SSH public key; "
                            "use an existing provider-issued identity or ask remote gateway to restore password-only access"
                        )
                    raise YeesuanRemoteError(f"remote gateway instance menu was not reached: {diagnostic}")

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
                raise YeesuanRemoteError(
                    "PEM key was accepted, but the keyboard-interactive 2FA password was rejected; "
                    "update the password file with the current remote gateway 2FA password"
                )
            if entered != 0:
                diagnostic = _diagnostic(chunks[-1])
                if "Key authentication required" in diagnostic or "Invalid key" in diagnostic:
                    raise YeesuanRemoteError(
                        "remote gateway rejected password-only authentication and now requires a registered SSH public key; "
                        "use an existing provider-issued identity or ask remote gateway to restore password-only access"
                    )
                raise YeesuanRemoteError(f"interactive shell was not reached: {diagnostic}")
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
        if self._uses_direct_identity():
            try:
                completed = subprocess.run(
                    ["scp", *args],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise YeesuanRemoteError(f"SCP transfer timed out after {timeout}s") from exc
            output = "\n".join(
                part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
            )
            return RemoteResult(command="scp", returncode=completed.returncode, output=output)
        pexpect = _load_pexpect()
        password = self._read_password()
        child = pexpect.spawn("scp", args, encoding="utf-8", timeout=timeout)
        chunks: list[str] = []
        try:
            matched = child.expect([r"(?i)password[^:]*:", r"密码[^:：]*[:：]", pexpect.EOF, pexpect.TIMEOUT])
            chunks.append(_redact(child.before or "", password))
            if matched >= 2:
                raise YeesuanRemoteError(f"SCP password or 2FA prompt was not reached: {_diagnostic(_redact(child.before or '', password))}")
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
                        raise YeesuanRemoteError(
                            "remote gateway requires the provider-issued PEM followed by keyboard-interactive 2FA; "
                            "update the 2FA password file or verify the identity file"
                        )
                    raise YeesuanRemoteError(f"SCP gateway authentication failed: {_diagnostic(diagnostic)}")
                if completed == 2:
                    last_percent = int(child.match.group(1))
                    if not 0 <= last_percent <= 100:
                        raise YeesuanRemoteError(f"invalid SCP progress marker: {last_percent}%")
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
                    raise YeesuanRemoteError("SCP transfer timed out before reporting progress")
                raise YeesuanRemoteError(f"SCP transfer stalled at {last_percent}%")
        finally:
            child.close(force=True)

    def _wrap_command(self, command: str) -> str:
        return f"source {_remote_path(self.config.environment_script)} && {command}"

    def _uses_direct_identity(self) -> bool:
        return bool(self.config.instance_id and self.config.identity_file)

    def _ssh_options(self, *, tty: bool) -> list[str]:
        options = ["-tt" if tty else "-T", "-p", str(self.config.port), "-o", f"User={self._login_user()}"]
        if self.config.host_key_policy == "strict":
            options += ["-o", "StrictHostKeyChecking=yes"]
        elif self.config.host_key_policy == "accept-new":
            options += ["-o", "StrictHostKeyChecking=accept-new"]
        else:
            raise YeesuanRemoteError("host_key_policy must be strict or accept-new")
        options += self._auth_options()
        return options

    def _auth_options(self) -> list[str]:
        if self.config.identity_file:
            identity = Path(self.config.identity_file).expanduser()
            if not identity.is_file():
                raise YeesuanRemoteError(f"SSH identity file does not exist: {identity}")
            options = [
                "-i",
                str(identity),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "PasswordAuthentication=no",
            ]
            if self._uses_direct_identity():
                options += [
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "KbdInteractiveAuthentication=no",
                    "-o",
                    "PreferredAuthentications=publickey",
                ]
            else:
                options += ["-o", "PreferredAuthentications=publickey,keyboard-interactive"]
            return options
        return [
            "-o",
            "PubkeyAuthentication=no",
            "-o",
            "PreferredAuthentications=password,keyboard-interactive",
        ]

    def _login_user(self) -> str:
        return f"{self.config.user}::{self.config.instance_id}" if self.config.instance_id else self.config.user

    def _read_password(self) -> str:
        if self.password_file is None:
            raise YeesuanRemoteError("legacy authentication requires an external password file")
        try:
            mode = self.password_file.stat().st_mode & 0o777
            if mode & 0o077:
                raise YeesuanRemoteError("password file must not be accessible by group or others")
            password = self.password_file.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise YeesuanRemoteError(f"cannot read password file: {exc}") from exc
        if not password:
            raise YeesuanRemoteError("password file is empty")
        return password
