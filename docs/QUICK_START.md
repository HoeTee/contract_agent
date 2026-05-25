# Quick Start

Use this guide to verify that the service can run end to end.

## 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

## 2. Create A Test User

```powershell
python scripts/manage_users.py create --username testuser --password Test123456 --display-name TestUser
```

If the user already exists, reset the password:

```powershell
python scripts/manage_users.py reset-password --username testuser --password Test123456
```

## 3. Add Review Criteria

Put the review criteria DOCX here:

```text
data/testuser/contract_review_criteria/criteria.docx
```

The filename must be:

```text
criteria.docx
```

## 4. Start The Web Service

```powershell
uvicorn app:app --host 0.0.0.0 --port 5000
```

Open:

```text
http://127.0.0.1:5000
```

Login:

```text
username: testuser
password: Test123456
```

## 5. Upload A Contract

Upload a real `.docx` contract from the web page.

If the review succeeds, the service writes files to:

```text
data/testuser/contracts/
data/testuser/reports_docx/
data/testuser/logs/
```

The page should show a download link for the annotated DOCX.

## 6. Docker Smoke Test

Make sure these exist on the server:

```text
.env
users.json
data/
```

Build and run:

```powershell
docker build -t deep-research-agent:latest .
docker compose up -d
```

Current compose mapping:

```text
http://127.0.0.1:8000
```

For external access through the server IP, change `docker-compose.yaml`:

```yaml
ports:
  - "8000:5000"
```

Then open:

```text
http://<server-ip>:8000
```

## 7. Expected Output

Uploaded contract:

```text
data/testuser/contracts/<task_prefix>_<original_filename>.docx
```

Annotated result:

```text
data/testuser/reports_docx/<task_prefix>_<contract_name>_批注版.docx
```

Task logs:

```text
data/testuser/logs/<YYYY-MM-DD>/<task>/
```
