FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# The build context is src/ (not src/cloud/) because sparky_relay imports
# sparky_contracts at module scope, and that package ships from src/shared/.
# Building from src/cloud/ produced an image that pulled and started cleanly but
# died on import with ModuleNotFoundError: No module named 'sparky_contracts',
# so the revision never passed its startup probe and Container Apps silently
# kept serving the previous revision.
COPY shared/pyproject.toml /build/shared/pyproject.toml
COPY shared/sparky_contracts /build/shared/sparky_contracts
COPY cloud/pyproject.toml /build/cloud/pyproject.toml
COPY cloud/sparky_relay /build/cloud/sparky_relay

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir /build/shared /build/cloud \
    && rm -rf /build \
    && apt-get update \
    && apt-get install -y --no-install-recommends libcap2-bin \
    && setcap 'cap_net_bind_service=+ep' /usr/local/bin/python3.11 \
    && apt-get purge -y --auto-remove libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 80

CMD ["/usr/local/bin/python3.11", "-m", "uvicorn", "sparky_relay.asgi:app", "--host", "0.0.0.0", "--port", "80"]
