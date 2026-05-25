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
