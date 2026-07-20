from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import PROJECT_ROOT, SESSION_SECRET_KEY
from endpoints.api.review_jobs import api_jobs_router
from endpoints.oa.review import oa_router
from endpoints.review.task_store import reconcile_interrupted_tasks
from endpoints.runtime.json_response import pretty_json_response
from endpoints.web.admin_routes import admin_router
from endpoints.web.user_routes import user_router


app = FastAPI(
    title="Contract Review Web",
    description="Web UI and API for uploading contracts and receiving review results.",
)

# Have session pass on the user id information across APIs
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="contract_review_session",
    max_age=None,
    same_site="lax",
    https_only=False
)

app.mount("/static", StaticFiles(directory=str(Path(PROJECT_ROOT) / "frontend" / "static")), name="static")
app.include_router(api_jobs_router)
app.include_router(oa_router)
app.include_router(user_router)
app.include_router(admin_router)


@app.on_event("startup")
def reconcile_tasks_on_startup() -> None:
    interrupted = reconcile_interrupted_tasks(reason="service_startup")
    if interrupted:
        print(f"[startup] marked {len(interrupted)} interrupted review task(s) as failed")


@app.get("/health")
def health():
    return pretty_json_response({"status": "ok"})
