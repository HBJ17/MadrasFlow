"""FastAPI app. Base path /api/v1, OpenAPI docs at /docs.

    uvicorn api.main:app --port 8000

Set DISABLE_SCHEDULER=1 to skip the background jobs (tests). If web/dist exists, the built PWA
is served from / so one process runs the whole demo.
"""
from __future__ import annotations

import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import routes_core, routes_ingest

PREFIX = "/api/v1"
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
CACHED_READS = ("/occupancy", "/forecast", "/history", "/wait-or-go", "/vehicle")


def _optional_routers():
    """Routers for later phases; imported lazily so the skeleton runs on its own."""
    out = []
    for name in ("routes_occupancy", "routes_plan", "routes_twin", "routes_stream", "routes_fleet"):
        try:
            mod = __import__(f"api.{name}", fromlist=["router"])
            out.append(mod.router)
        except ModuleNotFoundError as e:
            if e.name != f"api.{name}":
                raise
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched = None
    if os.environ.get("DISABLE_SCHEDULER") != "1":
        try:
            from api.jobs import start_scheduler
            sched = start_scheduler()
        except ModuleNotFoundError:
            pass
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="South Chennai Transit Occupancy API", version="0.1.0", lifespan=lifespan,
              docs_url="/docs", openapi_url=f"{PREFIX}/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=800)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if request.method == "GET" and path.startswith(PREFIX) and any(path[len(PREFIX):].startswith(p) for p in CACHED_READS):
        resp.headers["Cache-Control"] = "max-age=30"
    return resp


app.include_router(routes_core.router, prefix=PREFIX)
app.include_router(routes_ingest.router, prefix=PREFIX)
for r in _optional_routers():
    app.include_router(r, prefix=PREFIX)

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    mimetypes.add_type("application/manifest+json", ".webmanifest")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = WEB_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
