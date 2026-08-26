# syntax=docker/dockerfile:1.7

# STAGE 1: Compile, encrypt, and build the native loader.
FROM python:3.12-slim AS protect-builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /src

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        build-essential \
        cmake \
        libssl-dev \
        binutils \
    && rm -rf /var/lib/apt/lists/*

COPY packages/ /packages/
COPY protect/requirements.txt /tmp/protect-requirements.txt
RUN python -m pip install \
        --no-index \
        --find-links=/packages \
        -r /tmp/protect-requirements.txt

COPY . /src/

# The secret is available only to this build instruction. The generated header
# is compiled into the loader and removed before the instruction completes.
RUN --mount=type=secret,id=source_key,required=true \
    python /src/protect/pack.py \
        --root /src \
        --modules-file /src/protect/modules.txt \
        --key-file /run/secrets/source_key \
        --output /out/code.bin \
        --key-header /tmp/lexora-key/key_data.h \
    && cmake \
        -S /src/protect/loader \
        -B /tmp/loader-build \
        -DKEY_HEADER_DIR=/tmp/lexora-key \
        -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /tmp/loader-build --config Release --parallel \
    && install -m 0755 /tmp/loader-build/loader /out/loader \
    && rm -rf /tmp/lexora-key /tmp/loader-build


# STAGE 2: Final runtime image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=5 update \
    && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        vim \
        curl \
        dnsutils \
        iputils-ping \
        iproute2 \
        netcat-openbsd \
        procps \
        less \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY packages/ /packages/
RUN python -m pip install \
        --no-index \
        --find-links=/packages \
        -r /app/requirements.txt \
    && rm -rf /packages

# Protected backend code.
COPY --from=protect-builder /out/loader /app/loader
COPY --from=protect-builder /out/code.bin /app/code.bin

# Runtime resources that are intentionally readable or bind-mounted.
COPY frontend/ /app/frontend/
COPY agents/prompts/cn_prompts.yaml /app/agents/prompts/cn_prompts.yaml
COPY resources/criteria/criteria.docx /app/resources/criteria/criteria.docx
COPY tools/document/reporting/pandoc_xelatex_template.tex /app/tools/document/reporting/pandoc_xelatex_template.tex

RUN mkdir -p /app/data /app/profiles /app/logs /app/reports

EXPOSE 8000

CMD ["/app/loader", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
