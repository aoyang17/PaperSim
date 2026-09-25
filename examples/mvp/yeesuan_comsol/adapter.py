"""Construct the Yeesuan MVP solver from user-owned local configuration."""

from __future__ import annotations

from pathlib import Path

from papersim.comsol import ComsolBackend

from yeesuan_executor import YeesuanConfig, YeesuanExecutor


def build_backend(
    *,
    config: str | Path,
    password_file: str | Path | None = None,
    remote_root: str | None = None,
    suite: str = "full",
) -> ComsolBackend:
    """Return a COMSOL backend with a user-configured Yeesuan executor."""

    site = YeesuanConfig.load(config)
    executor = YeesuanExecutor(site, password_file)
    return ComsolBackend(
        executor,
        remote_root=remote_root or site.remote_case_root,
        suite=suite,
        solver_version=site.solver_version,
    )
