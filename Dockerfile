FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 botuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

RUN mkdir -p /app/vault && chown -R botuser:botuser /app

USER botuser

CMD ["python", "-m", "bot.main"]
