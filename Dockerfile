# syntax=docker/dockerfile:1
FROM python:3.14-slim

LABEL org.opencontainers.image.title="hh515lm-reboot" \
      org.opencontainers.image.description="Monitor i restart routera TCL HH515LM" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --no-log-init --uid 10001 --gid app --no-create-home app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=app:app router_restart.py ./

USER 10001:10001

ENTRYPOINT ["python", "/app/router_restart.py"]
CMD ["--monitor"]
