import os
import shutil

from aether_api.services.sandbox import RestrictedSubprocessSandbox

SBX_ROOT = "/tmp/aether-test-sandbox"


def make_sb(tmp_path) -> RestrictedSubprocessSandbox:
    # pytest's tmp_path tree is mode 0700; the unprivileged sandbox user must
    # be able to traverse the root, so use a dedicated traversable directory.
    shutil.rmtree(SBX_ROOT, ignore_errors=True)
    os.makedirs(SBX_ROOT, exist_ok=True)
    os.chmod(SBX_ROOT, 0o755)
    return RestrictedSubprocessSandbox(SBX_ROOT)


def test_basic_execution_drops_privileges(tmp_path):
    sb = make_sb(tmp_path)
    r = sb.run("import os\nprint(os.getuid())", workspace="t1")
    assert r.exit_code == 0
    uid = int(r.stdout.strip())
    assert uid != 0, "sandbox must not run as root"


def test_stdout_stderr_exit_code(tmp_path):
    sb = make_sb(tmp_path)
    r = sb.run("print('out'); import sys; print('err', file=sys.stderr); raise SystemExit(3)", workspace="t1")
    assert r.exit_code == 3
    assert "out" in r.stdout
    assert "err" in r.stderr


def test_wall_timeout_kills(tmp_path):
    sb = make_sb(tmp_path)
    r = sb.run("import time\ntime.sleep(30)", workspace="t1", timeout_s=2)
    assert r.timed_out is True
    assert r.exit_code != 0


def test_output_files_collected(tmp_path):
    sb = make_sb(tmp_path)
    r = sb.run("open('a.csv','w').write('x,y\\n1,2')", workspace="t1")
    assert r.exit_code == 0
    assert [(f.name, f.size) for f in r.files] == [("a.csv", 7)]


def test_workspace_isolation(tmp_path):
    sb = make_sb(tmp_path)
    sb.run("open('secret.txt','w').write('hidden')", workspace="ws_a")
    r = sb.run("import os\nprint(sorted(os.listdir('.')))", workspace="ws_b")
    assert "secret.txt" not in r.stdout


def test_memory_limit(tmp_path):
    sb = make_sb(tmp_path)
    r = sb.run("x = bytearray(900 * 1024 * 1024)", workspace="t1", memory_mb=256)
    assert r.exit_code != 0
    assert "MemoryError" in r.stderr


def test_cannot_write_outside_workspace(tmp_path):
    sb = make_sb(tmp_path)
    r = sb.run("open('/etc/aether_probe','w').write('x')", workspace="t1")
    assert r.exit_code != 0
    assert not os.path.exists("/etc/aether_probe")


def test_capabilities_are_honest(tmp_path):
    sb = make_sb(tmp_path)
    caps = sb.capabilities()
    assert caps["user_isolation"] is True
    assert caps["network_isolated"] in (True, False)
    assert caps["rlimits"] is True
    assert caps["provider"]
