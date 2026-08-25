# STAGE 1: Compile project Python source to bytecode
FROM python:3.12-slim AS bytecode-builder

WORKDIR /src

# Source only exists in the temporary builder stage.
COPY . .

# Compile foo.py to foo.pyc in the same directory.
# Embed /app paths in tracebacks, then remove the original source.
# -b：将 app.py 编译成同目录的 app.pyc
# -f：强制重新编译
# -q：减少构建输出
RUN python -m compileall \
        -b \
        -f \
        -q \
        -s /src \
        -p /app \
        /src \
    && find /src -type f -name '*.py' -delete \
    && rm -rf /src/packages


# STAGE 2: Final runtime image
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

RUN python -m pip install \
        --no-index \
        --find-links=/packages \
        -r requirements.txt \
    && rm -rf /packages

# Copy only the builder's current state.
# At this point project .py files have already been removed.
COPY --from=bytecode-builder /src/ /app/

# These directories are expected to be bind-mounted in deployments, but creating
# them keeps local container runs predictable when mounts are absent.
RUN mkdir -p /app/data /app/profiles

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
