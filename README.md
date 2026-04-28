# SmartLearner 2.0

Full-stack learning app with a **FastAPI** backend (JWT auth, SQLite, Groq-powered agents, RAG over book chunks) and a **React + Vite** frontend.

## Prerequisites

- **Python** 3.12+ (local backend)
- **Node.js** 22+ and npm (local frontend)
- **Docker** and Docker Compose (optional, all-in-one)
- **Groq API key** — copy `backend/.env.example` to `backend/.env` and set `GROQ_API_KEY`

## Local development

### Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API base: `http://localhost:8000` — OpenAPI docs at `/docs`. Health check: `GET /health`.

### Backend env notes

- `GROQ_API_KEY` is the primary key used by backend LLM calls.
- `GROQ_API_KEY_VALIDATORS` is optional for validator-only calls; if omitted, validators use `GROQ_API_KEY`.
- Gemini is not used as an LLM fallback in the backend runtime.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server defaults to `http://localhost:5173`. The app calls the API at `http://localhost:8000` (see `frontend/src/services/api.ts`).

## Docker Compose

From the repository root (after creating `backend/.env` from `.env.example`):

```bash
docker compose up --build
```

- **Backend:** `http://localhost:8000`
- **Frontend (nginx):** `http://localhost:8080`

The database file is stored in a Docker volume at `/data` inside the backend container (`DATABASE_URL` is set in `docker-compose.yml`). RAG assets ship from `backend/vector_db` in the image.

## Lesson and assessment behavior

- Lessons are generated dynamically and stored in the database.
- Quick Assessment uses 5 MCQ questions per attempt.
- If an attempt fails (below pass threshold), lesson content is regenerated with adaptation guidance and a fresh 5-question set is prepared from the updated lesson content.
- Adapted lesson content is preserved for retries instead of being overwritten on every lesson page refresh.

## Project layout

| Path | Role |
|------|------|
| `backend/app/` | FastAPI app, routes, agents, RAG |
| `backend/vector_db/` | Serialized chunks for retrieval |
| `frontend/src/` | React UI |

## License

Use and modify for your graduation project as required by your institution.
