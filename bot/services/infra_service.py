import os
import logging
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
