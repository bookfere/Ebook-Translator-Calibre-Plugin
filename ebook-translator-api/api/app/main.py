from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import close_pool, init_pool
from .routers import admin, jobs, metadata, uploads


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await init_pool(settings)
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(title="Ebook Translator API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(uploads.router)
app.include_router(jobs.router)
app.include_router(metadata.router)
app.include_router(admin.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
