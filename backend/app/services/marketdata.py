"""Market data: a pluggable price source plus a WebSocket fan-out hub.

The default ``SimulatedFeed`` moves marks with a small geometric random walk so the platform is
usable without vendor licences. In production, implement ``PriceSource`` against the licensed feed
(e.g. Bloomberg B-PIPE / BVAL, LSEG, PSE/PDEx) and set MPOWER_MARKET_SIM_ENABLED=false.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from datetime import datetime, timezone
from typing import Protocol

from fastapi import WebSocket
from starlette.concurrency import run_in_threadpool

from ..db import SessionLocal
from ..models import AssetClass, Instrument
from .compliance import run_post_trade_scan

log = logging.getLogger("mpower.marketdata")


class PriceSource(Protocol):
    def tick(self) -> list[dict]: ...


def _tick_row(i: Instrument) -> dict:
    chg = (i.price / i.prev_close - 1) * 100 if i.prev_close else 0
    return {"symbol": i.symbol, "price": i.price, "chg_pct": round(chg, 4), "ccy": i.ccy,
            "asset_class": i.asset_class.value}


def advance_prices(db, rng: random.Random, seconds: float) -> list[dict]:
    """Move every active mark by a random-walk step covering `seconds` of (accelerated) market time."""
    dt = max(seconds, 0) / (252 * 6.5 * 3600)  # fraction of a trading year
    out = []
    for i in db.query(Instrument).filter(Instrument.is_active.is_(True)).all():
        vol = i.vol if i.asset_class != AssetClass.FI else min(i.vol, 0.06)
        shock = rng.gauss(0, 1) * vol * math.sqrt(dt) * 8  # amplified for a lively demo
        i.price = round(max(i.price * math.exp(shock), 0.0001), 6)
        i.updated_at = datetime.now(timezone.utc)
        out.append(_tick_row(i))
    db.commit()
    return out


class SimulatedFeed:
    def __init__(self, tick_seconds: float, seed: int | None = None):
        self.seconds = tick_seconds
        self.rng = random.Random(seed)

    def tick(self) -> list[dict]:
        db = SessionLocal()
        try:
            return advance_prices(db, self.rng, self.seconds)
        finally:
            db.close()


# ---------------------------------------------------------------- serverless (poll) mode
_poll_rng = random.Random()
_last_scan = 0.0


def poll_ticks(db, tick_seconds: float, scan_every: float = 60.0) -> dict:
    """Serverless replacement for the feed loop: advance marks lazily when they are read.

    Marks move at most once per `tick_seconds` across all instances (the last update time lives in the
    database), and the post-trade / passive-breach scan runs at most once a minute per instance.
    """
    global _last_scan
    latest = db.query(Instrument.updated_at).order_by(Instrument.updated_at.desc()).limit(1).scalar()
    now = datetime.now(timezone.utc)
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    elapsed = (now - latest).total_seconds() if latest else tick_seconds
    if elapsed >= tick_seconds:
        # cap the step so a long idle period doesn't produce a huge jump
        ticks = advance_prices(db, _poll_rng, min(elapsed, tick_seconds * 3))
    else:
        ticks = [_tick_row(i) for i in db.query(Instrument).filter(Instrument.is_active.is_(True)).all()]
    scan = None
    mono = time.monotonic()
    if mono - _last_scan >= scan_every:
        _last_scan = mono
        scan = run_post_trade_scan(db)
    return {"ts": now.isoformat(), "data": ticks, "compliance": scan}


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.last: list[dict] = []

    async def connect(self, ws: WebSocket) -> None:
        """Register an already-accepted, authenticated socket."""
        self.clients.add(ws)
        if self.last:
            await ws.send_text(json.dumps({"type": "ticks", "data": self.last}))

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, msg: dict) -> None:
        text = json.dumps(msg)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001 - drop broken sockets
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()


async def run_feed(source: PriceSource, tick_seconds: float, scan_every: int = 15) -> None:
    n = 0
    while True:
        try:
            ticks = await run_in_threadpool(source.tick)
            hub.last = ticks
            await hub.broadcast({"type": "ticks", "ts": datetime.now(timezone.utc).isoformat(), "data": ticks})
            n += 1
            if n % scan_every == 0:  # periodic post-trade / passive breach scan
                db = SessionLocal()
                try:
                    res = await run_in_threadpool(run_post_trade_scan, db)
                    if res["opened"] or res["resolved"]:
                        await hub.broadcast({"type": "compliance", "data": res})
                finally:
                    db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - feed must survive transient errors
            log.exception("market feed iteration failed")
        await asyncio.sleep(tick_seconds)
