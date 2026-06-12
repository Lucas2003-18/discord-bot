FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Docker CLI + Compose plugin (estáticos) — usados por infra_service.rebuild_container
# para rodar `docker compose up -d --build` via socket montado em /var/run/docker.sock
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar xz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -fsSL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 \
       -o /usr/local/lib/docker/cli-plugins/docker-compose \
    && chmod +x /usr/local/bin/docker /usr/local/lib/docker/cli-plugins/docker-compose

RUN useradd -m -u 1000 botuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

RUN mkdir -p /app/vault && chown -R botuser:botuser /app

USER botuser

CMD ["python", "-m", "bot.main"]
