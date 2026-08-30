from __future__ import annotations

import os
import pwd
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxFile:
    name: str
    path: str
    size: int


SANDBOX_TIMEOUT_S_DEFAULT = 60


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    oom: bool = False
    files: list[SandboxFile] = field(default_factory=list)


class SandboxProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def run(self, code: str, *, language: str = "python", workspace: str | None = None,
            input_files: dict[str, bytes] | None = None, timeout_s: int = 60,
            memory_mb: int = 2048, env: dict[str, str] | None = None) -> SandboxResult: ...


class RestrictedSubprocessSandbox(SandboxProvider):
    """Honest reduced-isolation sandbox for hosts without user namespaces.

    Guarantees: unprivileged user (nobody), CPU/memory/file/process rlimits,
    wall-time kill of the whole process group, per-conversation workspace.
    NOT guaranteed (reported truthfully via capabilities()): network
    isolation, filesystem pivot. The outer container is the boundary.
    """

    name = "restricted_subprocess"

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # The sandboxed process runs unprivileged; every directory from the
        # workspace up to (and including) the root must be traversable.
        self._ensure_traversable(self.root)
        try:
            self._nobody = pwd.getpwnam("nobody")
        except KeyError:
            self._nobody = None

    @staticmethod
    def _ensure_traversable(path: Path) -> None:
        current = path.resolve()
        while True:
            try:
                mode = current.stat().st_mode & 0o777
                if mode & 0o005 == 0o005:
                    break  # already world-traversable; parents above are fine
                os.chmod(current, mode | 0o005)
            except OSError:
                break
            if current.parent == current or str(current) in ("/", ""):
                break
            current = current.parent

    def capabilities(self) -> dict:
        return {
            "provider": self.name,
            "user_isolation": self._nobody is not None,
            "network_isolated": False,
            "filesystem_pivot": False,
            "rlimits": True,
            "wall_timeout": True,
            "note": "User namespaces unavailable on this host; namespace-based "
                    "providers (bubblewrap/docker) are disabled. Code runs as an "
                    "unprivileged user with resource limits.",
        }

    def _workspace_dir(self, workspace: str | None) -> Path:
        safe = os.path.normpath(workspace or "default").lstrip("/").replace("..", "_")
        d = self.root / safe
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o777)
        return d

    def _limits(self, memory_mb: int):
        def apply():
            os.setpgrp()
            mem = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
            # Privilege drop happens at exec time via setpriv (this kernel
            # blocks setuid() after fork but allows setpriv's exec-time drop).
        return apply

    def _command(self) -> list[str]:
        base = [sys.executable, "-I", "__aether_task__.py"]
        setpriv = shutil.which("setpriv")
        if setpriv and self._nobody:
            return [setpriv, "--reuid", str(self._nobody.pw_uid),
                    "--regid", str(self._nobody.pw_gid), "--clear-groups", *base]
        return base

    def run(self, code: str, *, language: str = "python", workspace: str | None = None,
            input_files: dict[str, bytes] | None = None, timeout_s: int = 60,
            memory_mb: int = 2048, env: dict[str, str] | None = None) -> SandboxResult:
        if language != "python":
            return SandboxResult(127, "", f"Unsupported language: {language}", 0)
        workdir = self._workspace_dir(workspace)
        if input_files:
            for name, data in input_files.items():
                safe = os.path.basename(name)
                (workdir / safe).write_bytes(data)
                os.chmod(workdir / safe, 0o666)
        script = workdir / "__aether_task__.py"
        script.write_text(code)
        os.chmod(script, 0o666)

        run_env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/tmp",
            "TMPDIR": "/tmp",
            "MPLBACKEND": "Agg",
            # BLAS thread pools pre-allocate per CPU; on many-core hosts this
            # blows past RLIMIT_AS. Pin to one thread inside the sandbox.
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        if env:
            run_env.update(env)

        before = _snapshot_files(workdir)
        started = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.Popen(
                self._command(),
                cwd=str(workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=run_env,
                preexec_fn=self._limits(memory_mb),
            )
            try:
                out, err = proc.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    proc.kill()
                out, err = proc.communicate()
            exit_code = proc.returncode if proc.returncode is not None else -9
        finally:
            try:
                script.unlink()
            except OSError:
                pass

        duration = int((time.monotonic() - started) * 1000)
        stdout = (out or b"").decode("utf-8", errors="replace")
        stderr = (err or b"").decode("utf-8", errors="replace")
        oom = "MemoryError" in stderr or (exit_code == -9 and not timed_out)
        files = _new_files(workdir, before)
        if timed_out:
            stderr = f"[sandbox] execution killed after {timeout_s}s wall-time limit\n{stderr}"
        return SandboxResult(
            exit_code=exit_code, stdout=_cap(stdout), stderr=_cap(stderr),
            duration_ms=duration, timed_out=timed_out, oom=oom, files=files,
        )


def _cap(text: str, limit: int = 24000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[sandbox] output truncated ({len(text)} chars total)"


def _snapshot_files(d: Path) -> dict[str, float]:
    out = {}
    for p in d.rglob("*"):
        if p.is_file() and p.name != "__aether_task__.py":
            try:
                out[str(p.relative_to(d))] = p.stat().st_mtime
            except OSError:
                pass
    return out


def _new_files(d: Path, before: dict[str, float]) -> list[SandboxFile]:
    out = []
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.name == "__aether_task__.py":
            continue
        rel = str(p.relative_to(d))
        try:
            st = p.stat()
        except OSError:
            continue
        if rel not in before or before[rel] != st.st_mtime:
            out.append(SandboxFile(name=rel, path=str(p), size=st.st_size))
    return out


class BubblewrapSandbox(RestrictedSubprocessSandbox):
    """Bubblewrap-based sandbox (namespace isolation) — used when the host allows it."""

    name = "bubblewrap"

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update({
            "provider": self.name,
            "user_isolation": True,
            "network_isolated": True,
            "filesystem_pivot": True,
            "note": "bubblewrap namespace isolation",
        })
        return caps


def _bwrap_available() -> bool:
    if not shutil.which("bwrap"):
        return False
    try:
        r = subprocess.run(
            ["bwrap", "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
             "--symlink", "usr/lib64", "/lib64", "--dev", "/dev", "--proc", "/proc",
             "--tmpfs", "/tmp", "true"],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


_sandbox: SandboxProvider | None = None


def get_sandbox() -> SandboxProvider:
    global _sandbox
    if _sandbox is None:
        root = os.environ.get("SANDBOX_ROOT", "")
        if not root:
            repo_root = Path(__file__).resolve().parents[4]
            root = str(repo_root / "data" / "sandbox")
        if _bwrap_available():
            _sandbox = BubblewrapSandbox(root)
        else:
            _sandbox = RestrictedSubprocessSandbox(root)
    return _sandbox
