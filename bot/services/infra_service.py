import os
import logging
from datetime import datetime, timezone
import httpx

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
