FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install Python dependencies from the offline wheelhouse.
COPY requirements.txt .
COPY packages/ /packages/
RUN python -m pip install --no-index --find-links=/packages -r requirements.txt

# Copy application source. Runtime data and secrets are excluded by .dockerignore.
COPY . .

# These directories are expected to be bind-mounted in deployments, but creating
# them keeps local container runs predictable when mounts are absent.
RUN mkdir -p /app/data /app/user_profiles

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
