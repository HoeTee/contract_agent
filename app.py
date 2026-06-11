from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import PROJECT_ROOT, SESSION_SECRET_KEY
from web.admin_routes import admin_router
from web.routes import router


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

app.mount("/static", StaticFiles(directory=str(Path(PROJECT_ROOT) / "web" / "static")), name="static")
app.mount(
    "/docs-portal/assets",
    StaticFiles(directory=str(Path(PROJECT_ROOT) / "docs" / "portal" / "assets")),
    name="docs-portal-assets",
)
app.include_router(router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {"status": "ok"}
