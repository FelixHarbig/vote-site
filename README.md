# Teacher Voting Backend

A dockerized FastAPI-based backend for conducting teacher evaluations with PostgreSQL and Redis support. This system allows students to securely vote on teachers using one-time vote codes.

## 📋 Project Overview

This project provides a secure voting system where:

- **Admins** generate vote codes and manage teacher/vote data through database routes
- **Students** vote on teachers using a challenge-response verification system to prevent fraud
- **Vote codes** are single-use and challenge-based for security
- **Rate limiting** protects against brute-force attacks on vote codes
- **Caching** improves performance for teacher list queries

## 🔄 Voting Flow

### Student Voting Process

1. **Verify** (`POST /api/vote/verify`): Student submits vote code

   - Receives a 32-character challenge token
   - Rate limited to prevent code brute-forcing
2. **Solve** (`POST /api/vote/solve`): Student confirms challenge

   - Must submit both vote code and challenge
   - Returns list of available teachers
   - Teacher list is cached for performance
3. **Get Teachers** (`GET /api/vote/get_teachers`): Retrieve cached teacher list

   - Alternative endpoint if cache expires
   - Requires valid challenge
4. **Submit** (`POST /api/vote/submit`): Submit vote(s)

   - Can vote on multiple teachers at once
   - Both challenge and vote code are invalidated after submission
   - **Important**: All teachers must be submitted in a single request

### Frontend Implementation Notes

For optimal user experience:

- Auto-run challenge after vote code entry
- Cache challenge token and teacher list in localStorage/session storage
- Allow users to vote on multiple teachers across sessions without losing progress
- Show clear rate-limit warnings before users appempt multiple vote codes (48h ban)
- Aggregate all teacher votes before final submission

## 🔧 Environment Configuration

Create a `.env` file in the project root with the following variables:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@postgres:5432/voting_db
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_DB=voting_db
POSTGRES_HOST=postgres

# Redis Configuration (Caching & Session Management)
REDIS_URL=redis://:password@redis:6379
REDIS_PASSWORD=password
REDIS_HOST=redis

# Application Configuration
FRONTEND_URL=http://localhost:3000
ADMIN_SECRET=your_secret_admin_key_here
MAX_FAILED_ATTEMPTS=5
DEV=TRUE  # Set to FALSE in production
```

## Usage

### Local Development

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```
2. **Run development server**:

   ```bash
   python app/main.py
   ```
3. **Access the application**:

   - API: `http://localhost:8001`
   - Docs (dev only): `http://localhost:8001/docs`

## 📊 Database Schema

### Tables

| Table          | Purpose                                                  |
| -------------- | -------------------------------------------------------- |
| `teachers`   | Teacher profiles with subjects, descriptions, and images |
| `votes`      | Individual vote records with timestamps and IP tracking  |
| `images`     | Teacher profile images (stored as binary data)           |
| `vote_codes` | One-time use vote codes with challenge tracking          |

### Key Models

**Teachers**: Stores teacher information including name, subjects, gender, and profile images
**Votes**: Records votes with teacher_id, timestamp, overall rating, and IP address
**VoteCodes**: Tracks vote codes with continuation keys for challenge-response flow

## 🛠️ Development & Debugging

### Database Viewer

Access a visual database editor:

```bash
docker run -p 8081:8081 sosedoff/pgweb
```

Then visit `http://localhost:8081`

### Useful Alembic Commands

**Create migrations**:

```bash
alembic revision --autogenerate -m "describe your changes"
```

**Apply migrations**:

```bash
alembic upgrade head
```

**Rollback last migration**:

```bash
alembic downgrade -1
```

### Common Issues & Fixes

**Issue**: Docker build fails with psycopg2

- **Fix**: Ensure `requirements.txt` contains `psycopg2-binary` (not `psycopg2`)

**Issue**: Alembic can't find models

- **Fix**: Add `prepend_sys_path = ./app` to `alembic.ini`

**Issue**: Async PostgreSQL errors in Alembic

- **Fix**: Use synchronous connections in Alembic migrations (already configured)

## 🔒 Security Considerations

- **Rate Limiting**: Vote code verification is limited
- **Challenge-Response**: Prevents unauthorized votes without valid code
- **IP Tracking**: Votes are logged with IP addresses for auditing
- **Non-Root Docker User**: Container runs as `appuser` for security
- **CORS Configuration**: Restricted to specified frontend origins
- **Dev Mode**: Disables OpenAPI docs in production

## 🚨 Known Limitations & TODOs

- [ ] Missing additional vote criteria fields (TODO)
- [ ] No persistent volume configuration in docker-compose (you need to change this yourself)
- [ ] When using /admin/db/edit on the picture database there are some errors. In general, it is recommended to use edit_row.
- [ ] The .env variables could bee in a class which can be fetched.

## 💾 Docker Architecture Notes

The project uses Docker Compose with separate services:

- **PostgreSQL**: Primary data storage
- **Redis**: Caching and session management
- **Backend**: FastAPI application

This is a bit overkill though.

## 📝 Contributing

When making changes:

1. Create a new Alembic migration for database changes
2. Test the code
3. Follow existing code style (except if your's is better) and logging patterns

## 📄 License

TODO
