from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import review, history, upload

app = FastAPI(title="Contract Review API", version="1.0.0")

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