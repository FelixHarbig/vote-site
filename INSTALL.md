# Installation & Deployment Guide

This guide covers setting up the Teacher Voting Backend in various environments: Docker (recommended), local development, and production.

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Quick Start (Docker)](#quick-start-docker)
3. [Local Development (No Docker)](#local-development-no-docker)
4. [Configuration](#configuration)
5. [Supabase Setup (Optional)](#supabase-setup-optional)
6. [Database Migrations](#database-migrations)
7. [Creating an Admin Account](#creating-an-admin-account)
8. [Updating the Application](#updating-the-application)
9. [Production Deployment](#production-deployment)
10. [Linux-Specific Notes](#linux-specific-notes)
11. [Troubleshooting](#troubleshooting)
12. [Docker Command Reference](#docker-command-reference)

---

## Prerequisites

- **Docker & Docker Compose** (recommended): [Install Docker](https://docs.docker.com/get-docker/)
- **Or local installations**: PostgreSQL 16+, Redis 7+, Python 3.11+
- **Git** (optional, for cloning)

---

## Quick Start (Docker)

The fastest way to get running is using the provided Docker Compose configurations.

### Step 1: Prepare Environment

```bash
# Clone repository (if not already)
git clone https://github.com/yourusername/vote-site.git
cd vote-site

# Copy environment template
cp .env.example .env
```

Edit `.env` and set at minimum:
- `ADMIN_SECRET` - a strong random string for admin challenge
- `JWT_SECRET_KEY` - a long random string for JWT signing
- `FRONTEND_URL` - your frontend URL (e.g., `http://localhost:3000`)
- PostgreSQL & Redis passwords (defaults are `VotePass123` and `2` - change for production)

For Supabase integration, also set the `SUPABASE_*` variables (see [Supabase Setup](#supabase-setup-optional)).

### Step 2: Create Docker Network

The backend connects to database/redis via a shared network named `vote_internal`.

```bash
docker network create vote_internal || true  # ignore if already exists
```

### Step 3: Start Database & Redis

```bash
docker compose --env-file .env -f database_reddis_docker/docker-compose.yml up -d
```


*Note: --env-file .env is required here because the compose file uses ${POSTGRES_USER}, ${POSTGRES_DB}, and ${REDIS_PASSWORD} in its healthcheck and command fields.
Verify both containers are healthy:
```bash
docker compose --env-file .env -f database_reddis_docker/docker-compose.yml ps
# Wait until "postgres" and "redis" show State "Up" (not "starting")
```

### Step 4: Start Backend

```bash
docker compose -f backend_docker/docker-compose.yml up -d
```

The backend will:
- Connect to PostgreSQL and Redis
- Create database tables if they don't exist
- Initialize default settings (including `gdpr_enabled` and `supabase_auth_enabled`)

### Step 5: Run Database Migrations

The Alembic migrations need to be applied:

```bash
docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head
```

You should see output like:
```
INFO  [alembic.runtime.migration] Running upgrade -> initial_migration
INFO  [alembic.runtime.migration] Running upgrade add_continuaton_verification
...
```

### Step 6: Create Admin User

```bash
# Using Python directly in container:
docker compose -f backend_docker/docker-compose.yml exec backend python -m app.cli.create_admin --username admin --password "YourStrongPassword"
```

This generates a TOTP secret and QR code URI. Scan the QR code with Google Authenticator or similar app.

Alternatively, run from host (if you have Python deps installed):
```bash
python -m app.cli.create_admin --username admin --password "YourStrongPassword"
```

### Step 7: Verify Installation

Check logs:
```bash
docker compose -f backend_docker/docker-compose.yml logs -f backend
```

Look for:
- Redis connection successful
- Database connection successful
- FastAPI cache initialized
- Settings added to database

Test API health:
```bash
curl http://localhost:8000/
# {"message":"Why are you here?"}
```

If `DEV=TRUE` in .env, API docs are at: http://localhost:8000/docs

### Step 8: Access the Application

- **Backend API**: http://localhost:8000 (production) or http://localhost:8001 (when running `python app/main.py` locally)
- **API Docs** (only when `DEV=TRUE`): http://localhost:8000/docs
- **Admin login**: POST to `/api/auth/verify_totp` with username, password, and TOTP code
- **Voting flow**: See README.md

---

## Local Development (No Docker)

If you prefer running PostgreSQL and Redis directly on your machine (useful for debugging):

### Install Dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Also install Alembic for migrations
pip install alembic
```

### Set Up Local Database

```bash
# Create PostgreSQL database
createdb -U postgres votedb

# Optionally create dedicated user:
psql -c "CREATE USER voteuser WITH PASSWORD 'VotePass123';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE votedb TO voteuser;"
```

### Set Up Redis

```bash
# On Ubuntu/Debian:
sudo apt-get install redis-server
sudo systemctl start redis

# On macOS:
brew install redis
brew services start redis

# On Windows: use WSL or download Redis for Windows
```

### Configure Environment

Edit `.env`:
```env
DATABASE_URL=postgresql://voteuser:VotePass123@localhost:5432/votedb
REDIS_URL=redis://:your_redis_password@localhost:6379
FRONTEND_URL=http://localhost:3000
DEV=TRUE
# ... other vars
```

### Run Migrations

```bash
alembic upgrade head
```

### Start Backend

```bash
python app/main.py
```

Server starts on http://localhost:8001 with docs enabled.

---

## Configuration

All configuration is done via environment variables.

### Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | - | PostgreSQL connection URL |
| `REDIS_URL` | Yes | - | Redis connection URL (include password if required) |
| `FRONTEND_URL` | Yes | - | Frontend origin(s) for CORS (comma-separated) |
| `DEV` | No | `FALSE` | Set `TRUE` to enable dev mode (Swagger UI, relaxed CORS) |
| `ADMIN_SECRET` | Yes | - | Secret for admin challenge-response (any strong string) |
| `JWT_SECRET_KEY` | Yes | - | JWT signing secret (min 32 chars, random) |
| `JWT_ACCESS_TOKEN_EXPIRE_HOURS` | No | `12` | JWT token expiration time |
| `MAX_FAILED_ATTEMPTS` | No | `10` | IP ban threshold |
| `SUPABASE_URL` | Optional | - | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Optional | - | Supabase publishable (anon) key |
| `SUPABASE_SECRET_KEY` | Optional | - | Supabase secret (service role) key |
| `CONTROLLER_NAME` | Yes (GDPR) | - | Data controller name for imprint/privacy |
| `CONTROLLER_ADRESS` | Yes (GDPR) | - | Controller address (legal requirement) |
| `CONTROLLER_MAIL` | Yes (GDPR) | - | Controller email for data requests |
| `REDIS_PASSWORD` | Yes* | - | Redis password (used by Redis container) |
| `POSTGRES_USER` | Yes* | - | PostgreSQL username (used by Postgres container) |
| `POSTGRES_PASSWORD` | Yes* | - | PostgreSQL password |
| `POSTGRES_DB` | Yes* | - | PostgreSQL database name |
| `POSTGRES_HOST` | Yes* | - | PostgreSQL hostname in Docker (`postgres`) |

* Required only when running PostgreSQL/Redis in Docker (they read these env vars directly). If connecting to external DB/Redis, these may not be needed by the backend but are harmless.

### Feature Flags (Database Settings)

The following can be toggled via the `settings` table (or defaults are used):

- `gdpr_enabled` (default: `True`): Enables GDPR consent, export, and deletion endpoints
- `supabase_auth_enabled` (default: `True`): Enables Supabase authentication integration

You can change these via admin database management UI or directly in the database.

---

## Supabase Setup (Optional)

Supabase provides authentication and optional database hosting. You can run the backend without Supabase (local admin auth still works), but Supabase is recommended for user authentication.

### Create a Supabase Project

1. Sign up at [supabase.com](https://supabase.com)
2. Create a new project (choose region closest to your users)
3. Wait for initialization (~2 minutes)

### Get API Keys

In your Supabase project dashboard:
1. Go to **Settings → API**
2. Copy the following:
   - **Project URL** → `SUPABASE_URL`
   - **anon/public key** → `SUPABASE_PUBLISHABLE_KEY` (starts with `sb_publishable_`)
   - **service_role key** → `SUPABASE_SECRET_KEY` (starts with `sb_secret_`)

⚠️ **Keep `SUPABASE_SECRET_KEY` confidential** - it has admin privileges.

### Add Keys to `.env`

```env
SUPABASE_URL=https://xyzcompany.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_XXXXX
SUPABASE_SECRET_KEY=your_sb_secret_key_here
```

### (Optional) Use Supabase Database

Instead of running your own PostgreSQL container, you can use Supabase's managed Postgres:

```env
DATABASE_URL=postgresql://postgres:YOUR_DB_PASSWORD@db.your-project.supabase.co:5432/postgres
```

Then you **do not** need to start the `postgres` service via Docker Compose.

---

## Database Migrations

The project uses Alembic for database schema migrations.

### Applying Migrations

After code updates that include new migrations:

```bash
# With Docker:
docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head

# Local:
alembic upgrade head
```

### Creating a New Migration

If you modify database models in `app/database/models.py`:

```bash
alembic revision --autogenerate -m "describe your change"
```

Review the generated file in `alembic/versions/` to ensure it's correct, then commit it.

### Migration Files

- All migration files are in `alembic/versions/`
- They are applied in chronological order based on filename
- Never edit already-applied migration files; create new ones instead

---

## Creating an Admin Account

The system uses a local admin authentication with TOTP (2FA).

```bash
# With Docker:
docker compose -f backend_docker/docker-compose.yml exec backend python -m app.cli.create_admin --username <username> --password <password>

# Local:
python -m app.cli.create_admin --username <username> --password <password>
```

Output includes:
- TOTP secret (for manual entry)
- QR code URI (scan with authenticator app)
- Recovery code (save it!)

After creation, use `/api/auth/verify_totp` endpoint to log in and receive a JWT.

---

## Updating the Application

### Code-Only Changes (No Schema Update)

If you only changed Python code (no model changes):

1. Rebuild and restart the backend container:
   ```bash
   docker compose -f backend_docker/docker-compose.yml up -d --build
   ```

2. No need to restart the database or Redis - they remain running.

### Schema Changes (Migrations Required)

If you added new database columns or tables:

1. Generate migration:
   ```bash
   # Local development
   alembic revision --autogenerate -m "add new column"
   ```

2. Apply migration:
   ```bash
   docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head
   ```

3. Restart backend (if code changed):
   ```bash
   docker compose -f backend_docker/docker-compose.yml up -d --build
   ```

**Note**: Database migrations are designed to be non-destructive (nullable columns). They do not require full database restart; only the backend needs restarting to pick up new code.

### Quick Restart (No Rebuild)

If code is mounted as a volume (development) or you only changed config:

```bash
docker compose -f backend_docker/docker-compose.yml restart backend
```

---

## Production Deployment

### 1. Server Preparation

- Provision a Linux VPS (Ubuntu 22.04+ recommended)
- Install Docker & Docker Compose
- Open firewall ports: 8000 (backend API), optionally 5432 (PostgreSQL) if host-run

### 2. Copy Application

```bash
# Clone to server
git clone https://github.com/yourusername/vote-site.git
cd vote-site

# Checkout release tag or commit
git checkout v1.0.0
```

### 3. Configure Environment

```bash
cp .env.example .env
nano .env  # or use your editor
```

**Critical production settings**:
```env
DEV=FALSE
FRONTEND_URL=https://voting.yourdomain.com
DATABASE_URL=postgresql://voteuser:StrongPass@postgres:5432/votedb
REDIS_URL=redis://:StrongRedisPass@redis:6379
JWT_SECRET_KEY=<32+ random characters>
ADMIN_SECRET=<strong random string>
CONTROLLER_NAME=Your Name
CONTROLLER_ADRESS=Street, City, Country
CONTROLLER_MAIL=contact@yourdomain.com
```

### 4. Start Services

```bash
docker network create vote_internal || true
docker compose -f database_reddis_docker/docker-compose.yml up -d
docker compose -f backend_docker/docker-compose.yml up -d
```

### 5. Initialize Database

```bash
docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head
docker compose -f backend_docker/docker-compose.yml exec backend python -m app.cli.create_admin --username admin --password "<secure>"
```

### 6. Set Up Reverse Proxy (Optional but Recommended)

Use nginx or Caddy to expose port 80/443 and terminate TLS:

**nginx example**:
```nginx
server {
    listen 80;
    server_name voting.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name voting.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/voting.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/voting.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 7. Enable HTTPS with Let's Encrypt

```bash
sudo certbot --nginx -d voting.yourdomain.com
```

### 8. Monitoring & Logs

```bash
# View logs
docker compose -f backend_docker/docker-compose.yml logs -f backend

# Check container status
docker compose -f backend_docker/docker-compose.yml ps

# Database backups
docker compose --env-file .env -f database_reddis_docker/docker-compose.yml exec postgres pg_dump -U voteuser votedb > backup_$(date +%F).sql
```

### 9. Zero-Downtime Updates

When updating the backend:

```bash
# Pull new code
git pull origin main

# Rebuild and redeploy backend only (DB/Redis unaffected)
docker compose -f backend_docker/docker-compose.yml up -d --build

# If migrations changed:
docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head
```

---

## Linux-Specific Notes

### host.docker.internal Resolution

On Linux, `host.docker.internal` is not defined by default. The provided `backend_docker/docker-compose.yml` includes:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

This maps the hostname to the host's gateway IP automatically, enabling connectivity to host-run services (if you run PostgreSQL/Redis on the host instead of Docker). No further action needed.

If you prefer not to use `extra_hosts`, you can replace `host.docker.internal` in `.env` with your host's actual IP address (e.g., `192.168.1.100`).

### Permissions

Docker runs as rootless by default on many Linux distributions. If you encounter permission errors:

```bash
# Add your user to docker group (if not already)
sudo usermod -aG docker $USER
# Log out and back in
```

### SELinux/AppArmor

If you run into permission denied errors on volume mounts, you may need to adjust SELinux context or AppArmor profiles. Typically not needed on Ubuntu with default Docker installation.

---

## Troubleshooting

### Backend fails to start: "Database connection failed"

**Check**:
- `.env` has correct `DATABASE_URL` (host, port, user, password)
- PostgreSQL container is healthy: `docker compose --env-file .env -f database_reddis_docker/docker-compose.yml logs postgres`
- Network exists: `docker network ls | grep vote_internal`
- Try connecting manually: `docker compose --env-file .env -f database_reddis_docker/docker-compose.yml exec postgres psql -U voteuser -d votedb`

### Backend fails to start: "Redis connection failed"

**Check**:
- `REDIS_URL` includes password if required (`redis://:password@host:port`)
- Redis container is healthy: `docker compose --env-file .env -f database_reddis_docker/docker-compose.yml logs redis`
- Test connection: `docker compose --env-file .env -f database_reddis_docker/docker-compose.yml exec redis redis-cli -a 2 ping` (use your password)

### 500 Internal Server Error

View logs:
```bash
docker compose -f backend_docker/docker-compose.yml logs --tail 100 backend
```

Common causes:
- Missing migrations → run `alembic upgrade head`
- Settings not initialized → restart backend (it auto-creates defaults on startup)

### CORS Errors in Frontend

Ensure `FRONTEND_URL` in `.env` exactly matches the frontend origin (including port). When `DEV=TRUE`, localhost origins are automatically allowed.

### Migrations fail with "no such table" or "column already exists"

- Ensure you're running the correct migration sequence: `alembic upgrade head`
- If you manually edited migrations, check for conflicts
- Reset database (development only): `docker compose --env-file .env -f database_reddis_docker/docker-compose.yml down -v && docker compose --env-file .env -f database_reddis_docker/docker-compose.yml up -d` (⚠️ destroys all data)

### Cannot reach host.docker.internal from backend on Linux

Confirm `extra_hosts` is in `backend_docker/docker-compose.yml` (it should be). Verify:
```bash
docker compose -f backend_docker/docker-compose.yml exec backend cat /etc/hosts
# Should show: host.docker.internal host-gateway
```

### Port Already in Use

Change port mapping in `backend_docker/docker-compose.yml`:
```yaml
ports:
  - "8080:8000"   # hostPort:containerPort
```

---

## Docker Command Reference

| Task | Command |
|---|---|
| Start all services | `docker compose -f database_reddis_docker/docker-compose.yml up -d && docker compose -f backend_docker/docker-compose.yml up -d` |
| Stop all services | `docker compose -f database_reddis_docker/docker-compose.yml down && docker compose -f backend_docker/docker-compose.yml down` |
| Restart backend only | `docker compose -f backend_docker/docker-compose.yml restart backend` |
| Rebuild backend image | `docker compose -f backend_docker/docker-compose.yml up -d --build` |
| View logs (all) | `docker compose -f backend_docker/docker-compose.yml logs -f` |
| View logs (backend only) | `docker compose -f backend_docker/docker-compose.yml logs -f backend` |
| Execute command in backend | `docker compose -f backend_docker/docker-compose.yml exec backend <command>` |
| Run migrations | `docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head` |
| Create admin | `docker compose -f backend_docker/docker-compose.yml exec backend python -m app.cli.create_admin --username admin --password "<pwd>"` |
| Check container status | `docker compose -f backend_docker/docker-compose.yml ps` |
| Remove network (if needed) | `docker network rm vote_internal` |

---

## Updating the Backend (Quick Python Changes)

Small Python updates do NOT require restarting the database or Redis containers.

**Docker Compose workflow**:
```bash
# After pulling code changes or modifying files locally:
docker compose -f backend_docker/docker-compose.yml up -d --build
# This rebuilds the backend image and restarts only the backend container.
# PostgreSQL and Redis containers are untouched and keep their data.
```

**If only configuration changed** (e.g., `.env`):
```bash
docker compose -f backend_docker/docker-compose.yml restart backend
```

**If schema changed** (new migration):
```bash
docker compose -f backend_docker/docker-compose.yml exec backend alembic upgrade head
docker compose -f backend_docker/docker-compose.yml restart backend
```

**Local development** (without Docker for DB/Redis): simply restart `python app/main.py` or use `--reload` for auto-reload (only for development, not production).

---

## Support

For issues, check the Troubleshooting section above or open an issue on GitHub.
