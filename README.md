<div align="center">

# FinAlly

### _Your AI-Powered Trading Workstation_

![Status](https://img.shields.io/badge/status-in%20development-ecad0a?style=flat-square)
![Python](https://img.shields.io/badge/python-3.12-209dd7?style=flat-square&logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/next.js-15-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/fastapi-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-753991?style=flat-square)

**A Bloomberg-style terminal with an AI copilot that trades for you.**

Live-streaming prices. Simulated portfolio. Natural-language trade execution.
All in one dark, data-dense workstation.

[Quick Start](#-quick-start) • [Features](#-features) • [Architecture](#-architecture) • [Screenshots](#-screenshots)

</div>

---

## Screenshots

> _Coming soon — workstation UI, AI chat in action, portfolio heatmap._

<div align="center">
  <img src="planning/screenshots/workstation.png" alt="FinAlly workstation" width="80%" onerror="this.style.display='none'" />
</div>

---

## Features

<table>
<tr>
<td width="50%" valign="top">

### Live Market Data
Real-time price streaming over SSE with smooth green/red flash animations on every tick. Built-in GBM simulator out of the box — plug in a Massive API key for real data.

</td>
<td width="50%" valign="top">

### AI Trading Copilot
Chat with **FinAlly**, your AI assistant. Ask for analysis, get recommendations, or just say _"buy 10 shares of NVDA"_ — trades execute instantly.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Portfolio Visualizations
Treemap heatmap sized by weight and colored by P&L. Line chart tracking total portfolio value over time. Dense positions table with live unrealized P&L.

</td>
<td width="50%" valign="top">

### Terminal Aesthetic
Dark theme, monospace data grids, subtle animations. Every pixel earns its place. Desktop-first, tablet-friendly.

</td>
</tr>
</table>

---

## Quick Start

```bash
# 1. Configure
cp .env.example .env        # add your OPENROUTER_API_KEY

# 2. Launch
docker build -t finally .
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally

# 3. Trade
open http://localhost:8000
```

You land in with **$10,000 virtual cash** and a 10-ticker watchlist streaming live prices.

---

## Architecture

<div align="center">

| Layer            | Tech                                                   |
| :--------------- | :----------------------------------------------------- |
| **Frontend**     | Next.js 15 · TypeScript · Tailwind · Lightweight Charts |
| **Backend**      | FastAPI · Python 3.12 · uv · SSE                       |
| **Database**     | SQLite (lazy-initialized, volume-persisted)            |
| **AI**           | LiteLLM → OpenRouter · Cerebras inference · Structured outputs |
| **Market Data**  | GBM simulator _or_ Massive (Polygon.io) API            |
| **Packaging**    | Single multi-stage Docker image, port 8000             |

</div>

---

## Configuration

| Variable             | Required | Description                                           |
| :------------------- | :------: | :---------------------------------------------------- |
| `OPENROUTER_API_KEY` |    ✔️    | OpenRouter key for the AI chat assistant              |
| `MASSIVE_API_KEY`    |    —     | Polygon.io key for real market data (default: sim)    |
| `LLM_MOCK`           |    —     | `true` for deterministic mock LLM (tests & CI)        |

---

## Project Layout

```
finally/
├── frontend/    Next.js static export (TS + Tailwind)
├── backend/     FastAPI uv project (SSE + SQLite + LLM)
├── planning/    Agent contracts, PLAN.md, design docs
├── test/        Playwright E2E (docker-compose.test.yml)
├── scripts/     start / stop helpers (mac + windows)
└── db/          SQLite volume mount (runtime)
```

---

<div align="center">

**Built entirely by coding agents** as the capstone for an agentic AI coding course.

[LICENSE](LICENSE) · [PLAN.md](planning/PLAN.md)

</div>
