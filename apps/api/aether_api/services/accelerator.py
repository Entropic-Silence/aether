from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

_HY_SMI = "/opt/hyhal/bin/hy-smi"
_ROCM_SMI = "rocm-smi"
_NVIDIA_SMI = "nvidia-smi"


@dataclass
class AcceleratorInfo:
    kind: str = "none"  # none | cpu | cuda | rocm | hygon_dcu | auto
    backend: str = ""  # how the runtime exposes it (cuda / hip / cpu)
    driver: str = ""
    dtk_version: str = ""
    hip_version: str = ""
    torch_version: str = ""
    device_count: int = 0
    devices: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "backend": self.backend,
            "driver": self.driver,
            "dtk_version": self.dtk_version,
            "hip_version": self.hip_version,
            "torch_version": self.torch_version,
            "device_count": self.device_count,
            "devices": self.devices,
        }


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        ).stdout.strip()
    except Exception:
        return ""


def _read_dtk_version() -> str:
    for path in (
        "/opt/dtk/.info/version",
        "/opt/dtk/.info/version-libs",
        "/opt/dtk/.info/version-dev",
    ):
        try:
            with open(path) as f:
                value = f.read().strip()
                if value:
                    return value
        except Exception:
            continue
    return ""


def _read_hip_version() -> str:
    out = _run(["hipconfig", "--version"])
    if out:
        return out
    hip = shutil.which("hipconfig")
    if hip:
        out = _run([hip, "--version"])
    return out


def _torch_view() -> tuple[str, int, list[dict]]:
    """Return (backend, device_count, devices) as the runtime exposes them."""
    try:
        import torch  # type: ignore
    except Exception:
        return "cpu", 0, []
    version = getattr(torch, "__version__", "")
    if torch.cuda.is_available():
        devices = []
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            free, total = 0, props.total_memory
            try:
                free, total = torch.cuda.mem_get_info(i)
            except Exception:
                pass
            devices.append(
                {
                    "index": i,
                    "name": props.name,
                    "memory_total_mb": round(total / 1024 / 1024),
                    "memory_free_mb": round(free / 1024 / 1024),
                    "memory_used_mb": round((total - free) / 1024 / 1024),
                }
            )
        return "cuda", torch.cuda.device_count(), devices
    return "cpu", 0, []


def detect_accelerator() -> AcceleratorInfo:
    """Classify the accelerator without assuming NVIDIA.

    Hygon DCU is identified via /dev/kfd + hy-smi + DTK markers, even though
    DTK PyTorch exposes it through the CUDA API surface.
    """
    info = AcceleratorInfo()
    info.dtk_version = _read_dtk_version()
    info.hip_version = _read_hip_version()

    backend, count, devices = _torch_view()
    info.backend = backend
    info.device_count = count
    info.devices = devices
    try:
        import torch  # type: ignore

        info.torch_version = getattr(torch, "__version__", "")
    except Exception:
        pass

    has_kfd = os.path.exists("/dev/kfd")
    hy_smi_bin = _HY_SMI if os.path.exists(_HY_SMI) else shutil.which("hy-smi")

    if has_kfd and (info.dtk_version or hy_smi_bin):
        info.kind = "hygon_dcu"
        info.driver = "hyhal/DTK"
        _enrich_hygon(info, hy_smi_bin)
        return info

    if has_kfd:
        info.kind = "rocm"
        info.driver = "ROCm"
        return info

    if backend == "cuda" and shutil.which(_NVIDIA_SMI):
        info.kind = "cuda"
        info.driver = "NVIDIA"
        return info

    if backend == "cuda":
        info.kind = "cuda"
        return info

    info.kind = "cpu"
    info.backend = "cpu"
    return info


def _enrich_hygon(info: AcceleratorInfo, hy_smi_bin: str | None) -> None:
    """Overlay temperature/power/utilization from hy-smi onto torch devices."""
    if not hy_smi_bin:
        return
    out = _run([hy_smi_bin])
    if not out:
        return
    rows = []
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            rows.append(parts)
    for i, dev in enumerate(info.devices):
        if i < len(rows):
            r = rows[i]
            try:
                dev["temperature_c"] = float(r[1].replace("C", ""))
                dev["power_w"] = float(r[2].replace("W", ""))
                dev["power_cap_w"] = float(r[4].replace("W", ""))
                dev["vram_used_pct"] = float(r[5].replace("%", ""))
                dev["utilization_pct"] = float(r[6].replace("%", ""))
            except (IndexError, ValueError):
                pass


def get_utilization() -> dict:
    info = detect_accelerator()
    return {
        "kind": info.kind,
        "device_count": info.device_count,
        "devices": [
            {
                "index": d.get("index"),
                "utilization_pct": d.get("utilization_pct"),
                "memory_used_mb": d.get("memory_used_mb"),
                "memory_total_mb": d.get("memory_total_mb"),
                "temperature_c": d.get("temperature_c"),
            }
            for d in info.devices
        ],
    }
