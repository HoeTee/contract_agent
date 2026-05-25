# Deployment

## Build

```powershell
docker build -t deep-research-agent:latest .
```

## Run

```powershell
docker compose up -d
```

## Required Server Files

```text
.env
users.json
data/
```

`users.json` is mounted:

```yaml
- ./users.json:/app/users.json:ro
```

User data is mounted:

```yaml
- ./data:/app/data
```

## Healthcheck

The container listens on `5000`:

```text
http://127.0.0.1:5000/health
```
