# STAGE 1: Compile Python bytecode
FROM python:3.12-slim AS bytecode-builder

WORKDIR /src

# Source only exists in this temporary builder stage.
COPY . .

# Compile project modules to importable sourceless bytecode. Tracebacks retain
# their final /app paths rather than the temporary /src build paths.
RUN python -m compileall -b -f -q -s /src -p /app /src \
    && find /src -type f -name '*.py' -delete \
    && rm -rf /src/packages


# STAGE 2: Final image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        vim \
        curl \
        dnsutils \
        iputils-ping \
        iproute2 \
        netcat-openbsd \
        procps \
        less \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from the offline wheelhouse.
COPY requirements.txt .
COPY packages/ /packages/
RUN python -m pip install --no-index --find-links=/packages -r requirements.txt \
    && rm -rf /packages

# Copy the bytecode-only application tree from the builder stage.
COPY --from=bytecode-builder /src/ /app/

# These directories are expected to be bind-mounted in deployments, but creating
# them keeps local container runs predictable when mounts are absent.
RUN mkdir -p /app/data /app/profiles

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
