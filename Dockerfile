FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FEISHU_DATA_DIR=/app/data

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
COPY data/config.example.yaml /app/data/config.example.yaml

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

VOLUME ["/app/data"]

CMD ["feishu-msg-forwarder", "run", "poll", "--config-file", "/app/data/config.yaml"]
