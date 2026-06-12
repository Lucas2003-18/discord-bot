import asyncio
import os
import shlex
import logging
from datetime import datetime, timezone
import httpx
from bot import config

log = logging.getLogger(__name__)

_DOCKER_SOCK = "/var/run/docker.sock"
_HOST_PROC = "/host/proc"
_HOST_ROOT = "/host/root"


async def get_stopped_containers() -> list[dict]:
    transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=5) as client:
        resp = await client.get("/containers/json", params={"all": "true"})
        resp.raise_for_status()
        return [
            {"name": c["Names"][0].lstrip("/"), "status": c["Status"], "state": c["State"]}
            for c in resp.json()
            if c["State"] != "running"
        ]


async def get_containers() -> list[dict]:
    """Lista todos os containers (rodando ou não) via Docker socket."""
    transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=5) as client:
        resp = await client.get("/containers/json", params={"all": "true"})
        resp.raise_for_status()
        return [
            {
                "name": c["Names"][0].lstrip("/"),
                "image": c["Image"],
                "status": c["Status"],
                "state": c["State"],
            }
            for c in resp.json()
        ]


async def get_container_stats(name: str) -> dict:
    """Status detalhado de um container: status, contagem de restarts e uptime."""
    transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=5) as client:
        resp = await client.get(f"/containers/{name}/json")
        resp.raise_for_status()
        data = resp.json()

    state = data["State"]
    started_at = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
    uptime_seconds = max((datetime.now(timezone.utc) - started_at).total_seconds(), 0)

    return {
        "status": state["Status"],
        "restart_count": data.get("RestartCount", 0),
        "started_at": state["StartedAt"],
        "uptime_seconds": uptime_seconds,
    }


async def get_logs(name: str, lines: int = 100) -> str:
    """Lê o tail dos logs de um container."""
    transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=10) as client:
        resp = await client.get(
            f"/containers/{name}/logs",
            params={"stdout": "true", "stderr": "true", "tail": str(lines)},
        )
        resp.raise_for_status()
        return _demux_logs(resp.content)


def _demux_logs(raw: bytes) -> str:
    """Remove os headers de 8 bytes do stream multiplexado stdout/stderr do Docker.

    Containers com TTY não usam esse framing — se o primeiro byte não for
    um stream type válido (0/1/2), o conteúdo é tratado como texto puro.
    """
    if not raw:
        return ""

    out = []
    i = 0
    while i + 8 <= len(raw):
        if raw[i] not in (0, 1, 2):
            return raw.decode("utf-8", errors="replace")
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        start, end = i + 8, i + 8 + size
        if end > len(raw):
            return raw.decode("utf-8", errors="replace")
        out.append(raw[start:end])
        i = end

    return b"".join(out).decode("utf-8", errors="replace")


async def restart_container(name: str, confirmed: bool = False) -> dict:
    """Restart imediato via Docker API. Nunca executa sem confirmed=True."""
    if not confirmed:
        raise PermissionError("restart_container requer confirmed=True")

    transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=30) as client:
        resp = await client.post(f"/containers/{name}/restart")
        resp.raise_for_status()

    return {"action": "restart", "container": name, "ok": True}


async def rebuild_container(name: str, confirmed: bool = False) -> dict:
    """`docker compose up -d --build <service>` para o container.

    Descobre o projeto compose (config_files/working_dir/service) a partir
    das labels `com.docker.compose.*` do container, e traduz os caminhos do
    host para o que está montado em /host/root (read-only — suficiente para
    o daemon ler o build context).
    """
    if not confirmed:
        raise PermissionError("rebuild_container requer confirmed=True")

    transport = httpx.AsyncHTTPTransport(uds=_DOCKER_SOCK)
    async with httpx.AsyncClient(transport=transport, base_url="http://docker", timeout=10) as client:
        resp = await client.get(f"/containers/{name}/json")
        resp.raise_for_status()
        labels = resp.json()["Config"].get("Labels") or {}

    config_files = labels.get("com.docker.compose.project.config_files")
    working_dir = labels.get("com.docker.compose.project.working_dir")
    service = labels.get("com.docker.compose.service", name)

    if not config_files or not working_dir:
        raise RuntimeError(f"container '{name}' não foi criado via docker compose — rebuild não suportado")

    host_working_dir = _HOST_ROOT + working_dir
    host_config_files = ",".join(_HOST_ROOT + f for f in config_files.split(","))

    proc = await asyncio.create_subprocess_exec(
        "docker", "compose",
        "--project-directory", host_working_dir,
        "-f", host_config_files,
        "up", "-d", "--build", service,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    output = (stdout + stderr).decode("utf-8", errors="replace")

    if proc.returncode != 0:
        raise RuntimeError(output[-2000:])

    return {"action": "rebuild", "container": name, "ok": True, "output": output[-2000:]}


async def edit_file(path: str, old: str, new: str, confirmed: bool = False, **_ignored) -> dict:
    """Edita um arquivo no host via SSH (substituição simples old -> new).

    Necessário porque /host/root é montado read-only — escrita direta no
    filesystem do host não é possível de dentro do container. Requer
    INFRA_SSH_HOST/INFRA_SSH_USER/INFRA_SSH_KEY configurados.
    """
    if not confirmed:
        raise PermissionError("edit_file requer confirmed=True")

    ssh_base = [
        "ssh", "-i", config.INFRA_SSH_KEY,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        f"{config.INFRA_SSH_USER}@{config.INFRA_SSH_HOST}",
    ]

    read_proc = await asyncio.create_subprocess_exec(
        *ssh_base, "cat", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await read_proc.communicate()
    if read_proc.returncode != 0:
        raise RuntimeError(f"falha ao ler {path}: {stderr.decode('utf-8', errors='replace').strip()}")

    content = stdout.decode("utf-8")
    if old not in content:
        raise ValueError(f"texto não encontrado em {path}")
    new_content = content.replace(old, new, 1)

    write_proc = await asyncio.create_subprocess_exec(
        *ssh_base, f"cat > {shlex.quote(path)}",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await write_proc.communicate(new_content.encode("utf-8"))
    if write_proc.returncode != 0:
        raise RuntimeError(f"falha ao escrever {path}: {stderr.decode('utf-8', errors='replace').strip()}")

    return {"action": "edit_file", "path": path, "ok": True}


async def execute_action(action: str, container: str, confirmed: bool = False, **kwargs) -> dict:
    """Dispatcher central para ações de correção — nunca executa sem confirmed=True."""
    if not confirmed:
        raise PermissionError("execute_action requer confirmed=True")

    if action == "restart":
        return await restart_container(container, confirmed=True)
    if action == "rebuild":
        return await rebuild_container(container, confirmed=True)
    if action == "edit_file":
        return await edit_file(confirmed=True, **kwargs)

    raise ValueError(f"ação desconhecida: {action}")


def get_disk_usage() -> dict:
    st = os.statvfs(_HOST_ROOT)
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used_pct = round((total - free) / total * 100, 1)
    return {
        "total_gb": round(total / 1e9, 1),
        "free_gb": round(free / 1e9, 1),
        "used_pct": used_pct,
    }


def get_load_avg() -> tuple[float, float, float]:
    with open(f"{_HOST_PROC}/loadavg") as f:
        parts = f.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def get_cpu_cores() -> int:
    try:
        with open(f"{_HOST_PROC}/cpuinfo") as f:
            return sum(1 for line in f if line.startswith("processor"))
    except OSError:
        return os.cpu_count() or 1
