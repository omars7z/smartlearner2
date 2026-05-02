# Supabase with SmartLearner (backend)

## 1. Create the project

1. Go to [supabase.com](https://supabase.com) → **New project** (pick region, set a **database password** and save it).

## 2. Get the connection string (async)

1. In the dashboard: **Project Settings** (gear) → **Database**.
2. Under **Connection string**, choose **URI**.
3. Use **Direct connection** and port **5432** (good for a always-on FastAPI server on Railway/Render). Copy the string.

## 3. Turn it into the URL this app expects

- Replace the driver: the dashboard shows `postgresql://...`. This project uses **async** SQLAlchemy with `asyncpg`, so the start of the URL must be:

  `postgresql+asyncpg://`

- Example (shape only — your host is under **Project Settings → Database**):

  `postgresql+asyncpg://postgres:YOUR_PASSWORD@db.xxxxx.supabase.co:5432/postgres`

- **Password:** if it contains `@`, `#`, or spaces, you must [URL-encode](https://www.urlencoder.org/) the password, or set it in the connection UI so you get a copy-paste safe URI.

## 4. Set `.env` in `backend/`

```env
DATABASE_URL=postgresql+asyncpg://postgres:ENCODED_PASSWORD@db.XXXX.supabase.co:5432/postgres
SECRET_KEY=use-a-long-random-string-here
```

Do **not** commit `.env`. Keep `DATABASE_URL` on the server only.

## 5. Run once locally

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On startup, the app runs `create_all` and creates tables in Supabase. Check **Table Editor** in Supabase to see `users`, `courses`, etc.

## 6. Same login from any device (production)

- Host the **backend** with the same `DATABASE_URL` and `SECRET_KEY`.
- Build the **frontend** with `VITE_API_ORIGIN` pointing at that API’s origin (no path).
- Set `CORS_EXTRA_ORIGINS` on the backend to your deployed frontend URL (e.g. `https://your-app.vercel.app`).

## Notes

- **Pooler (port 6543):** this codebase disables asyncpg’s statement cache when using the pooler port so PgBouncer works. For **port 5432** direct, that extra setting is not applied.
- If SSL errors appear, the app already enables TLS for non-localhost PostgreSQL. You can force it with `DATABASE_SSL=true`.
