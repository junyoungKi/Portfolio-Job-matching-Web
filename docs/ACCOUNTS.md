<!-- Author: Joonyoung Ki -->
<!-- Purpose: Operator and developer notes for the login and wishlist features. -->

# Accounts: login and wishlist

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/auth/register` | `{email, password}`; logs the user in (sets cookie). 409 if the email exists. |
| POST | `/auth/login` | `{email, password}`; 401 on bad credentials, 429 when rate limited. |
| POST | `/auth/logout` | Clears the cookie (204). |
| GET | `/auth/me` | Current user, or 401 when anonymous. |
| GET | `/wishlist` | Saved jobs, newest first (login required). |
| POST | `/wishlist` | `{job_id}`; 201 when created, 200 if already saved. |
| DELETE | `/wishlist/{job_id}` | 204, idempotent. |

`GET /match/{resume_id}` now also returns the posting `id` for every result (all
existing fields are unchanged). Resume upload and matching still work without login.

## Server setup

1. Add to the server `.env` (see `.env.example`):
   - `JWT_SECRET` - at least 32 random characters. Without it `/auth/register`
     and `/auth/login` return 503; the rest of the app keeps working.
   - `COOKIE_SECURE=true` only after HTTPS is live (keep `false` on plain HTTP).
   - `TRUST_FORWARDED_FOR=true` only behind a trusted reverse proxy.
2. Rebuild the image (new dependencies `argon2-cffi`, `PyJWT`) and restart.
   The `users` and `wishlist_items` tables are created by the existing
   `create_all` call in the FastAPI lifespan; no manual migration is needed.
3. Changing `JWT_SECRET` logs everybody out.

## Tests

```bash
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/job_match_test pytest
```

The database name must contain `test` (tables are dropped and recreated).
