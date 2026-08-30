#!/usr/bin/env bash
# Read-only environment detection: Linux/CPU/RAM/Disk, Hygon DCU, DTK/ROCm/HIP,
# Python/Node/Docker, existing project directories. Prints an environment report.
set -uo pipefail

section() { printf "\n=== %s ===\n" "$1"; }

section "OS"
uname -a
grep PRETTY_NAME /etc/os-release 2>/dev/null

section "CPU / RAM / Disk"
echo "cores: $(nproc)"
grep -m1 "Vendor ID\|Model name" /proc/cpuinfo
free -h | sed -n '1,2p'
df -h / | sed -n '1,2p'

section "Hygon DCU"
if [ -e /dev/kfd ]; then
  echo "/dev/kfd present (kernel fusion driver)"
  ls /dev/dri 2>/dev/null
else
  echo "/dev/kfd not found"
fi
if command -v hy-smi >/dev/null 2>&1 || [ -x /opt/hyhal/bin/hy-smi ]; then
  (/opt/hyhal/bin/hy-smi 2>/dev/null || hy-smi) | head -12
else
  echo "hy-smi not found"
fi

section "DTK / ROCm / HIP"
[ -d /opt/dtk ] && echo "DTK at /opt/dtk -> $(readlink -f /opt/dtk)"
cat /opt/dtk/.info/version /opt/dtk/.info/version-libs 2>/dev/null | head -1
command -v hipconfig >/dev/null 2>&1 && hipconfig --version
command -v rocm-smi >/dev/null 2>&1 && echo "rocm-smi: present"

section "Python / torch"
python3 --version 2>&1
python3 - <<'PY' 2>/dev/null
try:
    import torch
    print("torch", torch.__version__)
    print("cuda_available", torch.cuda.is_available(), "device_count", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("device0", torch.cuda.get_device_name(0))
except Exception as e:
    print("torch not available:", e)
PY

section "Node / Docker"
node --version 2>&1 || echo "node not found"
npm --version 2>&1 || echo "npm not found"
docker --version 2>&1 || echo "docker not found"

section "Existing project dirs"
ls -la "$PWD" | head

echo
echo "[check] done (read-only)"
