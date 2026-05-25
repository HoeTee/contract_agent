# Project Structure

```text
deep_research_agent/
  README.md
  app.py
  main.py
  config.py
  users.example.json
  users.json

  agents/
  main_workflow/
  mcp_service/
  tools/
  scripts/
    manage_users.py

  loggers/
    resolve_review_task_paths.py
    workflow_logger.py
    agent_logger.py
    mcp_logger.py
    api_event_logger.py

  web/
    auth.py
    routes.py
    templates/
    static/

  docs/
    LOGGER_DESIGN.md
    USER_MANAGEMENT.md
    PROJECT_STRUCTURE.md
    DEPLOYMENT.md
    QUICK_START.md

  data/
    <username>/
      contract_review_criteria/
      institutional_docs/
      contracts/
      reports_docx/
      logs/
```

`data/` is persistent user data. `docs/` is Markdown documentation only.
