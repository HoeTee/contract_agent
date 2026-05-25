from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import PROJECT_ROOT, SESSION_SECRET_KEY
from web.routes import router


app = FastAPI(
    title="Contract Review Web",
    description="Web UI and API for uploading contracts and receiving review results.",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="contract_review_session",
    max_age=None,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=str(Path(PROJECT_ROOT) / "web" / "static")), name="static")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
