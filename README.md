# KFintech mPower — Investment Management & Portfolio Analytics

A full-stack buy-side platform for discretionary and institutional portfolio management: firm-wide positions,
maker-checker order workflow with pre-trade compliance, model portfolios with version control, drift-based
rebalancing, portfolio optimisation, risk & stress testing, post-trade / passive breach monitoring, back-office
settlement and reconciliation, audit trail and governance reporting — in a dense, dark trading-terminal UI.

![stack](https://img.shields.io/badge/API-FastAPI%20%2B%20SQLAlchemy%202-0f8f96) ![stack](https://img.shields.io/badge/Web-React%2019%20%2B%20TypeScript-18c4cc) ![stack](https://img.shields.io/badge/DB-PostgreSQL%2016-336791)

---

## Quick start

### Docker (recommended)

```bash
cp .env.example .env          # change the secrets
docker compose up --build
```

Open **http://localhost:8080** and sign in with a demo user (below). API docs: http://localhost:8080/api/docs

### Local development

```bash
# API  (Python 3.11+)
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000      # SQLite by default, migrations + demo data run on start

# Web  (Node 22+)
cd frontend
npm install
npm run dev                                      # http://localhost:5173, proxies /api and /ws to :8000
```

### Demo users

All demo users share the password set in `MPOWER_DEMO_PASSWORD` (default `Mpower@2026!`).

| User | Role | Typical use |
|---|---|---|
| `pm.santos` | PM | Maker: orders, model changes, rebalancing, optimiser |
| `pm.reyes` | PM | Checker: approves other PMs' / dealers' orders |
| `trader.lim` | TRADER | Dealer: order entry |
| `compliance.cruz` | COMPLIANCE | Rules, breach cases, model approval, order approval |
| `risk.tan` | RISK | Risk & stress, optimiser |
| `ops.garcia` | OPS | Settlement, reconciliation, static data (ratings, FX) |
| `admin` | ADMIN | Users, roles, entitlements (read-only on investment data) |
| `viewer` | VIEWER | Read-only |

---

## What it does (mapped to the BDO TIG RFI)

| RFI area | Where | Capability |
|---|---|---|
| 1. Portfolio construction & optimisation | Front Office → Optimizer | Max-Sharpe, minimum variance, target return, risk parity; min/max weights, asset-class bands, turnover penalty vs a live account; efficient frontier |
| | Front Office → Model Portfolios | Models with versioning, proposer ≠ approver, rationale, history, deployment to mapped accounts; client restrictions override model lines |
| | Front Office → Rebalancing | Drift vs active model version, tolerance bands, band/full modes, lot rounding, cost & transaction-tax estimates (e.g. PH stock transaction tax), proposal-level pre-trade compliance, batch staging for approval |
| 2. Decision support | My Portfolio, Account detail, Security Master | Cross-asset positions and exposure in reporting currency, live marks, ratings/ESG reference data, ⌘K search |
| 3. Compliance, risk & controls | Middle Office → Compliance Monitor / Rule Library | No-code rules (issuer/group, position, sector, asset-class band, rating floor, restricted list, leverage, duration, ESG floor, FX exposure, no-short, cash buffer) at global/entity/account scope; HARD (block) vs SOFT (override with reason); pre-trade, re-check at approval, scheduled post-trade scans, **passive breaches** from market/rating moves, case notes, auto-resolution; every rule change versioned |
| | Middle Office → Risk & Stress | Historical & parametric VaR, expected shortfall, volatility, duration, DV01, credit quality, concentration (issuer/sector/HHI), liquidity buckets, six historical/hypothetical scenarios plus custom shocks; security → account → entity views |
| | Back Office → Audit Trail | Append-only log of every change with before/after, user, IP and request ID |
| | System → Users & Roles | RBAC, entity entitlements, maker ≠ checker enforced server-side, account lockout, password policy |
| 4. Technology & integration | API | REST + OpenAPI, JWT (OAuth2 password flow), WebSocket market stream, CSV upload with validation, CSV exports, JSON structured logs, health/readiness probes, Alembic migrations, PostgreSQL |
| 5. Reporting | Reports → Report Centre | Holdings & valuation, breach register, trade ledger, audit trail exports |

## Architecture

```
┌──────────── web (nginx) ────────────┐        ┌──────────────── api (FastAPI) ────────────────┐
│ React 19 · TypeScript · Tailwind v4 │  /api  │ routers: auth · portfolio · orders · models   │
│ TanStack Query · WebSocket store    │ ─────► │          risk · compliance · ops · system     │
│ dense terminal theme                │  /ws   │ services: valuation · compliance engine ·     │
└─────────────────────────────────────┘ ─────► │   risk · optimiser (SciPy) · rebalance ·      │
                                                │   trading (maker-checker) · market feed       │
                                                └───────────────┬───────────────────────────────┘
                                                                │ SQLAlchemy 2 + Alembic
                                                         PostgreSQL 16 (SQLite for dev/tests)
```

Key design choices

- **One rule engine, three uses.** Rules evaluate a holdings *snapshot*, so the same definitions drive pre-trade
  checks (snapshot with hypothetical trades applied), post-trade scans and what-if/rebalance proposals. A trade only
  fails if it *causes or worsens* a breach; pre-existing breaches it does not worsen are reported as information.
- **Segregation of duties in the server**, not the UI: the maker of an order or model version can never approve it,
  and admins cannot act as maker/checker on investment decisions.
- **Re-check at approval.** Compliance is re-run when the checker approves, because markets and holdings move between
  entry and approval; failures auto-reject with an alert.
- **Derivatives**: exposure = full notional (as on the terminal), NAV contribution = MTM only.

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `MPOWER_ENV` | `development` | `production` refuses to start with the default JWT secret |
| `MPOWER_DATABASE_URL` | `sqlite:///./mpower.db` | e.g. `postgresql+psycopg://user:pass@host:5432/mpower` |
| `MPOWER_JWT_SECRET` | dev value | ≥ 32 chars; use `openssl rand -hex 32` |
| `MPOWER_ACCESS_TOKEN_MINUTES` | `60` | |
| `MPOWER_CORS_ORIGINS` | localhost | JSON list |
| `MPOWER_SEED_DEMO_DATA` | `true` | Set `false` outside demo environments |
| `MPOWER_DEMO_PASSWORD` | `Mpower@2026!` | Demo users only |
| `MPOWER_MARKET_SIM_ENABLED` | `true` | Simulated price feed; disable when a real feed is connected |
| `MPOWER_MARKET_TICK_SECONDS` | `2.0` | |

## Testing

```bash
cd backend && ruff check app tests && pytest -q                       # 27 tests: auth, RBAC, SoD, orders,
MPOWER_TEST_DATABASE_URL=postgresql+psycopg://… pytest -q              # compliance, risk, optimiser, models,
cd frontend && npm run typecheck && npm test && npm run build          # rebalancing, reconciliation, WebSocket
```

CI (`.github/workflows/ci.yml`) runs lint, tests on SQLite **and** PostgreSQL, the frontend typecheck/tests/build,
and a Docker build.

## Production readiness — what is real and what to plug in

Built and enforced: authentication, RBAC + entity entitlements, maker-checker, account lockout, audit trail,
input validation, migrations, structured logs with request IDs, health/readiness probes, security headers,
non-root containers, PostgreSQL support, CI.

Simulated for demonstration — replace before go-live:

1. **Market data** — `SimulatedFeed` random-walks marks and the seed generates synthetic price history (so optimiser
   and VaR figures are illustrative). Implement `PriceSource` against the licensed feed (Bloomberg B-PIPE/BVAL,
   LSEG, PSE/PDEx) and load real history.
2. **Execution** — `trading.execute()` fills at the mark. Replace with the OMS/EMS or broker FIX adapter and
   handle partial fills/allocations.
3. **Custody & accounting** — reconciliation accepts CSV statements; add SWIFT MT535/MT950 or ISO 20022 feeds and
   GL posting to the core ledger.
4. **Identity** — swap local passwords for SSO (SAML/OIDC) with MFA; move the login throttle to Redis behind a load
   balancer.
5. **Operations** — secrets in a vault, TLS termination, database backups/PITR, DR replica, log shipping/alerting,
   and penetration testing. Run the market feed in a single instance when scaling the API horizontally.
6. **Regulatory content** — the seeded BSP/mandate rules are illustrative; configure the rule library with TIG
   compliance for the actual limits and report formats.
