# crm-restaurant

A full-stack restaurant management system with a CRM dashboard, Telegram bots (public & staff), and a public-facing booking mini-app.

> **License:** [Business Source License 1.1](LICENSE) — free for non-commercial use; commercial use requires a license from the author.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                             │
│  Browser (CRM)   │  Telegram Mini App   │  Telegram Bots   │
└────────┬─────────┴───────────┬──────────┴────────┬─────────┘
         │                     │                   │
         ▼                     ▼                   │
┌────────────────┐   ┌──────────────────┐          │
│  CRM Frontend  │   │  App Frontend    │          │
│  Next.js 14    │   │  Next.js 14      │          │
│  (port 3001)   │   │  (port 3000)     │          │
└───────┬────────┘   └────────┬─────────┘          │
        │                     │                    │
        └──────────┬──────────┘                    │
                   ▼                               ▼
        ┌──────────────────────┐    ┌──────────────────────┐
        │   Backend (FastAPI)  │    │  Telegram Bot Public  │
        │   Python 3.12        │◄───│  aiogram 3 (port 8001)│
        │   port 8000          │    └──────────────────────┘
        │                      │    ┌──────────────────────┐
        │   REST API + WS      │    │  Telegram Bot Staff   │
        │   JWT + CSRF auth    │◄───│  aiogram 3 (port 8002)│
        └──────┬───────────────┘    └──────────────────────┘
               │
       ┌───────┼──────────┐
       ▼       ▼          ▼
┌──────────┐ ┌────────┐ ┌───────────┐
│ Postgres │ │ Redis  │ │  Strapi   │
│    16    │ │   7    │ │  CMS      │
│(port5432)│ │(port   │ │(port 1339)│
└──────────┘ │  6379) │ └───────────┘
             └────────┘
```

### Services

| Service | Description | Port |
|---|---|---|
| `backend` | FastAPI REST API + WebSocket | 8000 |
| `crm-frontend` | Staff CRM dashboard (Next.js) | 3001 |
| `app-frontend` | Public Telegram Mini App (Next.js) | 3000 |
| `telegram-bot-public` | Customer-facing Telegram bot (aiogram 3) | 8001 |
| `telegram-bot-staff` | Staff notification Telegram bot (aiogram 3) | 8002 |
| `strapi` | Headless CMS (restaurants, menus, events) | 1339 |
| `postgres` | Primary relational database | 5432 |
| `redis` | Cache, pub/sub for real-time events | 6379 |

---

## Tech Stack

### Backend (`crm-dev/backend`)
- **Python 3.12** + **FastAPI** — async REST API
- **SQLAlchemy 2 (async)** + **asyncpg** — ORM + PostgreSQL driver
- **Alembic** — database migrations
- **Pydantic v2** + **pydantic-settings** — validation & config
- **python-jose** — JWT authentication
- **bcrypt** — password hashing
- **Redis** (via aioredis) — caching, rate limiting, WebSocket pub/sub
- **structlog** — structured logging
- **WebSockets** — real-time table/booking state updates

### CRM Frontend (`crm-dev/frontend`)
- **Next.js 14** (App Router) — React 18 SSR/CSR
- **SCSS Modules** — component-scoped styles
- **WebSocket client** — live CRM updates

### Telegram Bots
- **aiogram 3** — async Telegram Bot framework
- **asyncpg** — direct PostgreSQL access
- **Redis pub/sub** — booking event notifications

### Infrastructure
- **Docker** + **Docker Compose** — full local & production orchestration
- **PostgreSQL 16** — primary database
- **Redis 7** — cache & message broker
- **Strapi 5** — headless CMS for content management (excluded from this repo)
- **Nginx** (external) — reverse proxy / TLS termination

---

## Repository Structure

```
.
├── crm-dev/
│   ├── backend/           # FastAPI application
│   │   ├── app/
│   │   │   ├── api/v1/    # REST endpoints (admin + public)
│   │   │   ├── core/      # Config, security, background tasks
│   │   │   ├── db/        # Models, session, migrations
│   │   │   ├── middleware/ # Auth, rate limiting, security headers
│   │   │   ├── schemas/   # Pydantic request/response schemas
│   │   │   ├── services/  # Business logic
│   │   │   └── websocket/ # WS handlers
│   │   ├── .env.example
│   │   └── Dockerfile
│   └── frontend/          # CRM Next.js app
│       ├── app/           # App Router pages
│       ├── components/    # UI components
│       ├── hooks/
│       └── utils/
├── telegram-bot-public/   # Public customer bot
├── telegram-bot-staff/    # Staff notification bot
├── docker-compose.yml     # Full stack orchestration
└── LICENSE
```

> **Note:** `app-dev/frontend` (public mini-app) and `strapi-dev` (CMS) are maintained in separate repositories and are excluded from this repo.

---

## Getting Started

### Prerequisites
- Docker 24+ and Docker Compose v2
- Git

### 1. Clone the repository

```bash
git clone https://github.com/RoberPascal/crm-restaurant.git
cd crm-restaurant
```

### 2. Configure environment variables

```bash
# Backend
cp crm-dev/backend/.env.example crm-dev/backend/.env
# Edit crm-dev/backend/.env with your values

# Telegram bots — create .env in each bot directory
# See telegram-bot-public/config.py and telegram-bot-staff/config.py for required vars
```

Required variables (see `.env.example` for full list):

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `CRM_SECRET_KEY` | JWT secret (≥32 chars, generate with `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `CRM_STRAPI_PUBLIC_URL` | Strapi CMS URL |
| `CRM_STRAPI_API_TOKEN` | Strapi API token |
| `CRM_TELEGRAM_BOT_TOKEN` | Telegram bot token (from @BotFather) |
| `TELEGRAM_BOT_TOKEN` | Public bot token |
| `POSTGRES_PASSWORD` | Shared DB password |

### 3. Start all services

```bash
POSTGRES_PASSWORD=your_password docker compose up -d
```

### 4. Initialize admin user

```bash
docker compose exec backend python scripts/init_admin.py
```

---

## Security

- JWT + CSRF double-token authentication
- HTTP-only secure cookies
- Rate limiting per IP (Redis-backed)
- Security headers (CSP, HSTS, X-Frame-Options)
- All secrets loaded from environment variables — no hardcoded credentials
- `admin-credentials.txt` is listed in `.gitignore` and must never be committed

---

## License

This project is licensed under the [Business Source License 1.1](LICENSE).  
Free for non-commercial use. Commercial use requires explicit permission from the author.  
The license converts to MIT on **2029-01-01**.

© 2026 Rober Pascal
