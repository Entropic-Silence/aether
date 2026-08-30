from fastapi import APIRouter, Depends

from ..deps import require_admin
from ..orm import User
from ..services.accelerator import detect_accelerator, get_utilization
from ..services.sandbox import SANDBOX_TIMEOUT_S_DEFAULT, get_sandbox

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/compute")
async def compute(_: User = Depends(require_admin)):
    info = detect_accelerator()
    return info.to_dict()


@router.get("/utilization")
async def utilization(_: User = Depends(require_admin)):
    return get_utilization()


@router.get("/sandbox")
async def sandbox_info(_: User = Depends(require_admin)):
    sb = get_sandbox()
    return {"capabilities": sb.capabilities(), "default_timeout_s": SANDBOX_TIMEOUT_S_DEFAULT}


@router.post("/sandbox/test")
async def sandbox_test(_: User = Depends(require_admin)):
    sb = get_sandbox()
    result = sb.run("print(6*7)", workspace="__admin_selftest__", timeout_s=20)
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()[:500],
        "duration_ms": result.duration_ms,
    }
