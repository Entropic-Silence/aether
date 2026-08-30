# Sandbox Protocol

Isolated execution for code the model writes. The Agent Runtime never runs
model-generated code in the host shell.

## Provider interface

```
SandboxProvider {
  create(spec) -> SandboxHandle
  exec(handle, {language, code, files, timeout}) -> SandboxResult
  write_file / read_file(handle, path)
  destroy(handle)
}

SandboxResult { exit_code, stdout, stderr, files[], duration_ms, oom }
```

Implementations (all behind the same interface): `Docker`, `Podman`,
`nsjail`, `Firecracker`, `Kubernetes Job`, remote Sandbox API, and the
current environment's default: **bubblewrap** (apt-installable, no Docker
needed on this DCU host).

## Resource limits (enforced per sandbox)

CPU, RAM, disk, wall time, process count, file-access scope.
**Network OFF by default**; only explicitly network-approved tools open it.

## Code verification loop

```
Generate code → Execute → capture stdout/stderr + exit code
  → if failed: LLM debugs → retry (bounded) → return verified result
```

UI shows live status: `Running code / Ran Python / Checking output`.

## Data analysis

CSV/XLSX/JSON/Parquet/SQLite handled with pandas/polars inside the sandbox;
outputs (tables, charts, generated files) return as artifacts for preview,
download, and Library save.

## Host specifics (this deployment)

No Docker, and user namespaces are disabled in this container
(`bwrap: Creating new namespace failed: Operation not permitted`). Detection
runs at startup: if bubblewrap works it is used; otherwise the active
provider is **restricted_subprocess**:

- code runs as `nobody`, never root
- rlimits: address space (per-execution MB cap), CPU, NPROC, FSIZE, NOFILE
- wall-time kill of the whole process group
- per-conversation persistent workspace; attached files injected by name;
  generated files collected and imported to the Library
- BLAS pinned to one thread (`OPENBLAS_NUM_THREADS=1` etc.) — required on the
  128-core DCU host or OpenBLAS pre-allocation blows the memory rlimit

**Reported honestly in Admin → Sandbox:** on this host network isolation and
filesystem pivot are NOT available; the outer container is the boundary. The
`capabilities()` dict drives that page — nothing is assumed or hidden.

