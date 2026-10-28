import { useSyncExternalStore } from "react";
import { api, tokenStore } from "./api";
import type { Tick } from "./types";

type Listener = () => void;

/**
 * Live market data. 'stream' mode (Docker / always-on server): WebSocket with exponential-backoff reconnect.
 * 'poll' mode (serverless, e.g. Vercel): fetch /market/ticks on an interval.
 */
class MarketStore {
  private ticks: Tick[] = [];
  private bySymbol = new Map<string, Tick>();
  private listeners = new Set<Listener>();
  private ws: WebSocket | null = null;
  private retry = 0;
  private timer: number | undefined;
  private ping: number | undefined;
  status: "connecting" | "live" | "offline" = "offline";
  compliance = 0; // increments when a compliance scan changes breaches

  private poller: number | undefined;
  private started = false;

  start() {
    if (this.started || !tokenStore.get()) return;
    this.started = true;
    this.setStatus("connecting");
    api<{ mode: "stream" | "poll"; interval_ms: number }>("/market/config")
      .then((cfg) => (cfg.mode === "poll" ? this.poll(cfg.interval_ms) : this.connect()))
      .catch(() => this.connect());
  }

  private poll(interval: number) {
    let failures = 0;
    const once = async () => {
      if (!this.started) return;
      try {
        const r = await api<{ data: Tick[]; compliance: { opened: number; resolved: number } | null }>("/market/ticks");
        failures = 0;
        this.ticks = r.data;
        this.bySymbol = new Map(r.data.map((t) => [t.symbol, t]));
        if (r.compliance && (r.compliance.opened || r.compliance.resolved)) this.compliance += 1;
        this.status = "live";
      } catch {
        failures += 1;
        this.status = failures > 2 ? "offline" : "connecting";
      }
      this.emit();
      this.poller = window.setTimeout(once, document.hidden ? interval * 4 : interval);
    };
    once();
  }

  stop() {
    this.started = false;
    window.clearTimeout(this.poller);
    window.clearTimeout(this.timer);
    window.clearInterval(this.ping);
    this.ws?.close();
    this.ws = null;
    this.setStatus("offline");
  }

  private connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/market`);
    this.ws = ws;
    this.setStatus("connecting");
    ws.onopen = () => {
      // authenticate in-band so the token never appears in URLs or access logs
      ws.send(JSON.stringify({ type: "auth", token: tokenStore.get() }));
      this.retry = 0;
      this.setStatus("live");
      this.ping = window.setInterval(() => ws.readyState === 1 && ws.send("ping"), 25_000);
    };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "ticks") {
        this.ticks = msg.data;
        this.bySymbol = new Map(this.ticks.map((t: Tick) => [t.symbol, t]));
      } else if (msg.type === "compliance") {
        this.compliance += 1;
      }
      this.emit();
    };
    ws.onclose = (ev) => {
      window.clearInterval(this.ping);
      this.ws = null;
      this.setStatus("offline");
      if (ev.code === 4401 || !tokenStore.get() || !this.started) return;
      const delay = Math.min(30_000, 1000 * 2 ** this.retry++);
      this.timer = window.setTimeout(() => this.connect(), delay);
    };
  }

  private setStatus(s: MarketStore["status"]) {
    this.status = s;
    this.emit();
  }

  private version = 0;
  private emit() {
    this.version++;
    this.listeners.forEach((l) => l());
  }

  subscribe = (l: Listener) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };
  getVersion = () => this.version;
  all = () => this.ticks;
  get = (s: string) => this.bySymbol.get(s);
}

export const market = new MarketStore();

export function useMarket() {
  useSyncExternalStore(market.subscribe, market.getVersion);
  return market;
}
