# Teacher Voting Backend

A secure, dockerized backend for teacher evaluations using FastAPI, PostgreSQL, and Redis.

## Project Overview

- **Admins**: Secure management via TOTP (Time-based One-Time Password) and JWT authentication.
- **Students**: Fraud-resistant voting using a challenge-response system.
- **Security**: Comprehensive rate limiting, IP tracking, and single-use vote codes.
- **Performance**: Redis caching for high-load endpoints.

## Admin Authentication

The system uses a secure 2FA implementation for administrative access.

### Creating an Admin
To create a new admin account with TOTP protection:

```bash
python -m app.cli.create_admin --username <username> --password <password>
```

This will generate a TOTP secret and QR code URI. Scan this with an authenticator app (e.g., Google Authenticator) to complete setup.

### Authentication Flow
1. **Login**: POST credentials + TOTP code to `/api/auth/verify_totp`.
2. **Token**: Receive a JWT Bearer token.
3. **Access**: Include `Authorization: Bearer <token>` in headers for all `/api/admin/*` endpoints.

## Voting Flow

1. **Verify** (`POST /api/vote/verify`): Submit vote code to receive a challenge token.
2. **Solve** (`POST /api/vote/solve`): Submit code + challenge to unlock teacher list.
3. **Vote** (`POST /api/vote/submit`): Submit ratings for one or more teachers. The code is invalidated upon success.

## Environment Configuration

Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql://user:pass@postgres:5432/voting_db

# Redis
REDIS_URL=redis://:pass@redis:6379

# Security
JWT_SECRET_KEY=change_this_to_a_secure_random_string
JWT_ACCESS_TOKEN_EXPIRE_HOURS=12
ADMIN_SECRET=your_secret_admin_key_here

# Application
FRONTEND_URL=http://localhost:3000
DEV=FALSE
```

## Usage

### Local Development

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run server**:
   ```bash
   python app/main.py
   ```

3. **Access API**:
   - URL: `http://localhost:8001`
   - Docs: `http://localhost:8001/docs` (only when DEV=TRUE)

## Database Management

- **Viewer**: Run `docker run -p 8081:8081 sosedoff/pgweb` to browse data at `http://localhost:8081`.
- **Migrations**: Use Alembic for schema changes.
  - Apply: `alembic upgrade head`
  - Create: `alembic revision --autogenerate -m "message"`

## Security Features

- **Rate Limiting**: Strict limits on verification and submission endpoints.
- **Anti-Abuse**: automatic IP banning for repeated failed attempts.
- **Input Validation**: All inputs validated via Pydantic models.
- **Secure Headers**: CORS restricted to configured origins.
