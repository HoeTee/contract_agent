# User Management

User accounts are stored in `users.json` at the project root.

Passwords are not stored as plaintext. The service stores PBKDF2 password hashes. If a user forgets a password, the administrator resets it to a new password.

## Create User

```powershell
python scripts/manage_users.py create --username user001 --password Abc123456 --display-name ZhangSan
```

The script creates:

```text
data/user001/
  contract_review_criteria/
  institutional_docs/
  contracts/
  reports_docx/
  logs/
```

## Reset Password

```powershell
python scripts/manage_users.py reset-password --username user001 --password NewPass123
```

## Disable Or Enable

```powershell
python scripts/manage_users.py disable --username user001
python scripts/manage_users.py enable --username user001
```

## Login Session

The web UI uses a signed session cookie to keep the user identity across requests.

`app.py` enables `SessionMiddleware`:

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="contract_review_session",
    max_age=None,
)
```

When `POST /login` succeeds, `web/routes.py` writes the authenticated user into the session:

```python
request.session["username"] = user["username"]
request.session["display_name"] = user.get("display_name") or user["username"]
```

`SessionMiddleware` signs that session data and sends it back to the browser as the `contract_review_session` cookie. Later requests to `/work`, `/review`, `/history`, and `/download/...` carry that cookie automatically. The server restores `request.session` from the cookie and reads:

```python
username = request.session.get("username")
```

That username is the trusted user partition key for:

```text
data/<username>/contracts/
data/<username>/reports_docx/
data/<username>/logs/
data/<username>/contract_review_criteria/criteria.docx
```

The browser sends the same cookie name for every user, but the cookie value is different per browser session. Therefore concurrent users do not share one server-side session. Each request is mapped from its own signed cookie to its own `request.session`.

Do not pass `username` from upload or download forms as the authority for file access. The username used for storage must come from `request.session`, not from user-controlled form data.

## Review Criteria

Each user needs a review criteria file:

```text
data/<username>/contract_review_criteria/criteria.docx
```

## Institutional Documents

Institutional documents, if enabled later, should live under:

```text
data/<username>/institutional_docs/
```
