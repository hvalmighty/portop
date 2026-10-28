"""mPower API - application factory, middleware, lifecycle and WebSocket market stream."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api import auth, compliance_api, models_api, ops, orders, portfolio, risk_api, system
from .audit import client_ip_var, request_id_var
from .config import get_settings
from .db import SessionLocal, engine
from .security import decode_token
from .services.compliance import run_post_trade_scan
from .services.marketdata import SimulatedFeed, hub, run_feed

settings = get_settings()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"ts": self.formatTime(record), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        rid = request_id_var.get()
        if rid:
            base["request_id"] = rid
        for k in ("method", "path", "status", "ms", "user"):
            if hasattr(record, k):
                base[k] = getattr(record, k)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base)


def _configure_logging() -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h]
    root.setLevel(settings.log_level)


log = logging.getLogger("mpower")


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parent.parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    run_migrations()
    if settings.seed_demo_data:
        from .seed import seed

        db = SessionLocal()
        try:
            if seed(db):
                log.info("demo dataset seeded")
            run_post_trade_scan(db)
        finally:
            db.close()
    task = None
    if settings.market_sim_enabled:
        task = asyncio.create_task(run_feed(SimulatedFeed(settings.market_tick_seconds), settings.market_tick_seconds))
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="KFintech mPower API",
    version="1.0.0",
    description="Investment management, compliance, risk and portfolio analytics",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_id_var.set(rid[:40])
    client_ip_var.set(request.client.host if request.client else None)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
    ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if request.url.path not in ("/healthz", "/readyz"):
        log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code, "ms": ms})
    return response


API = "/api/v1"
for r in (auth.router, portfolio.router, orders.router, models_api.router, risk_api.router, compliance_api.router,
          ops.router, system.router):
    app.include_router(r, prefix=API)


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
def readyz():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "unavailable", "error": type(exc).__name__}, status_code=503)
    return {"status": "ready", "market_feed": settings.market_sim_enabled, "ws_clients": len(hub.clients)}


@app.websocket("/ws/market")
async def market_ws(ws: WebSocket):
    """Clients authenticate in-band: first message must be {"type": "auth", "token": "<jwt>"} within 5s."""
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
    except (TimeoutError, ValueError, WebSocketDisconnect):
        await ws.close(code=4401)
        return
    if not isinstance(first, dict) or decode_token(str(first.get("token") or "")) is None:
        await ws.close(code=4401)
        return
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive pings from the client
    except WebSocketDisconnect:
        hub.disconnect(ws)
