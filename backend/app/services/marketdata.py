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


class SimulatedFeed:
    def __init__(self, tick_seconds: float, seed: int | None = None):
        self.dt = tick_seconds / (252 * 6.5 * 3600)  # fraction of a trading year
        self.rng = random.Random(seed)

    def tick(self) -> list[dict]:
        db = SessionLocal()
        try:
            out = []
            for i in db.query(Instrument).filter(Instrument.is_active.is_(True)).all():
                vol = i.vol if i.asset_class != AssetClass.FI else min(i.vol, 0.06)
                shock = self.rng.gauss(0, 1) * vol * math.sqrt(self.dt) * 8  # amplified for a lively demo
                i.price = round(max(i.price * math.exp(shock), 0.0001), 6)
                i.updated_at = datetime.now(timezone.utc)
                chg = (i.price / i.prev_close - 1) * 100 if i.prev_close else 0
                out.append({"symbol": i.symbol, "price": i.price, "chg_pct": round(chg, 4), "ccy": i.ccy,
                            "asset_class": i.asset_class.value})
            db.commit()
            return out
        finally:
            db.close()


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
