"""FastAPI giriş noktası."""
from __future__ import annotations

import datetime as dt
import logging
from collections import deque

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware

from .billing.routes import router as billing_router
from .api.routes.matches import router as matches_router
from .updates import router as updates_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("edge.access")

app = FastAPI(title="Edge Analytics API", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Son isteklerin halka tamponu — telefonun neyi ne zaman istediğini görmek için.
_RECENT: deque[dict] = deque(maxlen=50)


@app.middleware("http")
async def _trace(request: Request, call_next):
    started = dt.datetime.now(dt.timezone.utc)
    response = await call_next(request)
    entry = {
        "at": started.isoformat(),
        "method": request.method,
        "path": request.url.path,
        "query": dict(request.query_params),
        "status": response.status_code,
        "ua": request.headers.get("user-agent", ""),
        "client": request.client.host if request.client else "",
    }
    _RECENT.append(entry)
    log.info("%s %s?%s -> %s (ua=%s)", entry["method"], entry["path"],
             entry["query"], entry["status"], entry["ua"][:60])
    return response


app.include_router(billing_router)
app.include_router(matches_router, prefix="/v1")
app.include_router(updates_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/_debug/requests")
def debug_requests():
    """Sunucuya gelen son 50 isteği döndürür (geçici tanı ucu)."""
    return {"count": len(_RECENT), "recent": list(reversed(_RECENT))}
