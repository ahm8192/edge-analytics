"""FastAPI giriş noktası."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from .billing.routes import router as billing_router
from .api.routes.matches import router as matches_router
from .updates import router as updates_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Edge Analytics API", version="0.2.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(billing_router)
app.include_router(matches_router, prefix="/v1")
app.include_router(updates_router)


@app.get("/health")
def health():
    return {"status": "ok"}
