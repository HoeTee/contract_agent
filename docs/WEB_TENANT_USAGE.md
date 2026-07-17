# Web Multi-Tenant Usage

This document describes the current `/web` tenant model, local data layout, CLI operations, and frontend behavior.

## Direct Conclusion

`/web` is tenant-scoped. Tenants and tenant users are managed by CLI. The frontend login form requires a `tenant_id`, username, and password. Runtime review data is stored under `data/web/<tenant_id>/<task_id>/`.

## Identity Files

Tenant registry:

```text
user_profiles/
  tenant_profiles.json
```

Tenant users and user review criteria:

```text
user_profiles/
  tenants/
    <tenant_id>/
      user_profiles.json
      criteria/
        <username>.docx
```

Meaning:

- `tenant_profiles.json` stores tenant records: `tenant_id`, display `name`, enabled status, and timestamps.
- `tenants/<tenant_id>/user_profiles.json` stores users for one tenant only.
- `tenants/<tenant_id>/criteria/<username>.docx` stores that user's default review criteria.

Plaintext passwords are not stored. User passwords are stored as password hashes through `endpoints/runtime/auth.py`.

## Runtime Data

Web review task data is stored as:

```text
data/
  web/
    <tenant_id>/
      <task_id>/
        task.json
        input/
        output/
        logs/
```

Task directory meaning:

- `task.json`: task metadata, including `tenant_id`, `tenant_name`, `username`, status, file names, and timestamps.
- `input/`: uploaded contract and optional uploaded criteria for this task.
- `output/`: reviewed DOCX result.
- `logs/`: workflow, conversation, MCP, and API event logs.

There is no `/users` or `/tasks` layer under `data/web/`.

## Tenant CLI

Create a tenant:

```bash
python scripts/manage_tenants.py create --tenant-id tenant_a --name "Tenant A"
```

List tenants:

```bash
python scripts/manage_tenants.py list
```

Disable or enable a tenant:

```bash
python scripts/manage_tenants.py disable --tenant-id tenant_a
python scripts/manage_tenants.py enable --tenant-id tenant_a
```

Delete a tenant profile:

```bash
python scripts/manage_tenants.py delete --tenant-id tenant_a
```

Boundary: deleting a tenant profile does not delete tenant users or task data. It removes the registry entry only.

## User CLI

Every user command requires `--tenant-id`.

Create a tenant admin:

```bash
python scripts/manage_users.py create --tenant-id tenant_a --username admin --password "ChangeMe123" --role admin --display-name "Tenant Admin"
```

Create a normal user:

```bash
python scripts/manage_users.py create --tenant-id tenant_a --username alice --password "ChangeMe123" --role user --display-name "Alice"
```

List users in one tenant:

```bash
python scripts/manage_users.py list --tenant-id tenant_a
```

Change role:

```bash
python scripts/manage_users.py set-role --tenant-id tenant_a --username alice --role admin
```

Reset password:

```bash
python scripts/manage_users.py reset-password --tenant-id tenant_a --username alice --password "NewPassword123"
```

Disable or enable a user:

```bash
python scripts/manage_users.py disable --tenant-id tenant_a --username alice
python scripts/manage_users.py enable --tenant-id tenant_a --username alice
```

Delete a user profile:

```bash
python scripts/manage_users.py delete --tenant-id tenant_a --username alice
```

Boundary: deleting a user profile does not delete existing task data in `data/web/<tenant_id>/`.

## Frontend Login

The login page is:

```text
/web/login
```

Login input:

- `tenant_id`
- username
- password

After login:

- `role=user` enters `/web/work`.
- `role=admin` enters `/web/admin`.
- The top-right user area shows the tenant name and current user.

The tenant is stored in the server-side session auth context. Users can only see task records under their own tenant and username.

## Tenant Admin Frontend

Tenant admins use `/web/admin`.

Current admin frontend scope:

- List users in the current tenant.
- Create users in the current tenant.
- Enable, disable, delete, reset password, and change role for users in the current tenant.
- View current tenant user review history.
- Download, upload, or restore a user's default review criteria.
- View task API event logs for tasks in the current tenant.

There is no super-admin frontend in the current implementation. Cross-tenant control is intentionally handled by CLI.

## Review Workflow

Normal user flow:

1. Login with `tenant_id`, username, and password.
2. Open `/web/work`.
3. Upload a contract DOCX.
4. Optionally upload review criteria DOCX for this task.
5. The system creates `data/web/<tenant_id>/<task_id>/`.
6. `task.json` starts as `queued`, then changes to `running`, then `completed` or `failed`.
7. The result DOCX is written to `output/`.
8. `/web/history` reads task records from `data/web/<tenant_id>/*/task.json`.

If no per-task criteria file is uploaded, the workflow uses:

```text
user_profiles/tenants/<tenant_id>/criteria/<username>.docx
```

## Deployment Notes

For Docker deployments, distinguish these locations:

- Development machine: local source and local `data/`, `user_profiles/`.
- Remote host: the machine running Docker.
- Service container: the running app container.
- Temporary management container or host shell: where CLI commands may be executed.

Persistent data must be mounted into the service container. The service needs long-term access to:

```text
user_profiles/
data/
```

Recommended compose mounts:

```yaml
volumes:
  - ./user_profiles:/app/user_profiles
  - ./data:/app/data
```

Input files come from browser uploads. The service writes task input, output, logs, and task metadata into the mounted `data/web/<tenant_id>/<task_id>/` directory. Tenant and user CLI commands write identity configuration into the mounted `user_profiles/` directory.

Do not write tenant profiles or task data only into a running container's temporary filesystem. If the container is recreated, that data will be lost.

## Quick Start

On the machine or management container that has the project code and mounted `user_profiles/`:

```bash
python scripts/manage_tenants.py create --tenant-id tenant_a --name "Tenant A"
python scripts/manage_users.py create --tenant-id tenant_a --username admin --password "ChangeMe123" --role admin
python scripts/manage_users.py create --tenant-id tenant_a --username alice --password "ChangeMe123" --role user
```

Then open:

```text
http://<host>/web/login
```

Login as:

```text
tenant_id: tenant_a
username: alice
password: ChangeMe123
```
