import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import review, history, upload
from mcp_service.mcp_server.mcp_server import mcp, warmup_llamaindex_engine


mcp_app = mcp.streamable_http_app()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        await asyncio.to_thread(warmup_llamaindex_engine)
        yield


app = FastAPI(title="Contract Review API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


app.mount("/", mcp_app)
