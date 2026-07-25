# AI Chatbot

A multi-LLM chatbot. The frontend is a React + Vite single-page app; the backend is a FastAPI service that streams responses from multiple models via [OpenRouter](https://openrouter.ai), with input/output guardrails and structured error handling.

Live demo: [https://chatbot-whyvineet.vercel.app](https://chatbot-whyvineet.vercel.app)

## Tech stack

### Backend

- Python (`>=3.14`, see `backend/.python-version`)
- [FastAPI](https://fastapi.tiangolo.com/) (`fastapi[standard]`) : HTTP API + SSE streaming
- [httpx](https://www.python-httpx.org/) : async streaming client to OpenRouter
- [uv](https://docs.astral.sh/uv/) : dependency management and running (`backend/pyproject.toml`, `backend/uv.lock`)
- [OpenRouter](https://openrouter.ai) : single API surface for multiple LLM providers

### Frontend

- [React 19](https://react.dev/)
- [Vite](https://vitejs.dev/)
- [Tailwind CSS 4](https://tailwindcss.com/) (via `@tailwindcss/vite`)
- ESLint (React Hooks + React Refresh configs)

## Architecture

```plain
React frontend (Vite, :5173)
        |  POST /chat (SSE stream)
        v
FastAPI backend (:8000)
  - guardrails/input.py           -> validates message + model before anything runs
  - sessions/manager.py           -> in-memory per-session chat history
  - guardrails/system_prompt.py   -> injects safety system message
  - clients/openrouter.py         -> streams the completion, retries once on 5xx
  - guardrails/output.py          -> rejects empty/malformed model output
  - exceptions.py                 -> maps every failure to a JSON error + status code
        |  HTTPS request
        v
OpenRouter API
        |  routes by model key (config/models.py)
        v
Gemini 2.5 Flash / GPT-4o / Llama 3.1 8B / Qwen 3.5 Flash
```

Everything the backend knows about a model, its OpenRouter model string, display name, temperature, and max tokens — lives in `backend/config/models.py` as a single `MODELS` dict. Adding a new model is a new dict entry; no other code changes.

### Backend layout

```plain
backend/
├── main.py              # FastAPI app, CORS, exception handlers, router
├── api/routes.py         # /health, /models, /session/new, /session/{id}, /chat
├── clients/openrouter.py # streaming client with timeout + single retry on 5xx
├── config/
│   ├── models.py         # model registry (MODELS dict)
│   └── settings.py       # env-driven settings
├── exceptions.py          # ChatbotError hierarchy + FastAPI exception handlers
├── guardrails/
│   ├── system_prompt.py   # injects safety system message
│   ├── input.py           # message/model validation before a request runs
│   └── output.py          # rejects empty or malformed model responses
├── schemas/               # pydantic request/response models
└── sessions/manager.py    # in-memory session store with history trimming
```

### Frontend layout

```plain
frontend/
└── src/
    ├── App.jsx    # chat UI, session lifecycle, SSE stream consumption
    ├── main.jsx   # React root
    └── index.css
```

## Prerequisites

- Python `>=3.14`
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed
- Node.js (for `npm`/Vite) — Node 20+ recommended for Vite 8 / React 19
- An [OpenRouter](https://openrouter.ai/keys) API key

## Backend setup (uv + FastAPI)

```bash
cd backend

# Install dependencies from pyproject.toml / uv.lock into a local venv
uv sync
```

Create a `backend/.env` file (read by `config/settings.py` via `python-dotenv`). Only `OPENROUTER_API_KEY` is required, everything else has a default:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
APP_REFERER=http://localhost:8000
APP_TITLE=AI Chatbot API
REQUEST_TIMEOUT_SECONDS=30
MAX_MESSAGE_LENGTH=4000
MAX_HISTORY_MESSAGES=20
CORS_ORIGINS=http://localhost:5173
```

Run the API:

```bash
uv run fastapi dev main.py
```

The API comes up on `http://localhost:8000`. Key endpoints (see `api/routes.py`):

| Method | Path              | Purpose                                                      |
| ------ | ----------------- | ------------------------------------------------------------ |
| GET    | `/health`         | Liveness check                                               |
| GET    | `/models`         | List available model keys + display names                    |
| POST   | `/session/new`    | Create a chat session, returns`session_id`                   |
| DELETE | `/session/{id}`   | Clear a session's history                                    |
| POST   | `/chat`           | Send`{session_id, model, message}`, get back an SSE stream   |

## Frontend setup (Vite + React)

```bash
cd frontend
npm install
```

Create a `frontend/.env` with the backend URL, since `App.jsx` reads `import.meta.env.VITE_API_BASE_URL` directly and has no built-in fallback:

```env
VITE_API_BASE_URL=http://localhost:8000
```

Run the dev server:

```bash
npm run dev
```

The app comes up on `http://localhost:5173` (Vite's default) and talks to the backend at `VITE_API_BASE_URL`.

Other scripts (`frontend/package.json`):

```bash
npm run build     # production build
npm run preview   # preview the production build locally
npm run lint      # ESLint
```

## Running both together

1. Start the backend: `cd backend && uv run fastapi dev main.py`
2. Start the frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173`. On load, the frontend calls `/session/new` and `/models`; if the backend isn't reachable, the UI surfaces `can't reach backend at <VITE_API_BASE_URL>` instead of failing silently.

## Guardrails

- **Input** (`guardrails/input.py`): rejects empty or whitespace-only messages, messages over `MAX_MESSAGE_LENGTH`, and any `model` key not present in `config/models.py`.
- **Output** (`guardrails/output.py`): rejects an empty model response, and rejects a response that looks like a raw provider error object leaking through as content.

## Error handling

Every failure mode maps to a specific `ChatbotError` subclass with its own HTTP status code (`exceptions.py`): invalid requests (400), unsupported model (400), missing session (404), guardrail violation (422), provider rate limit (429), provider timeout (504), provider unavailable (502), and an unhandled-exception fallback (500). Mid-stream, `/chat` sends the same information as an SSE `error` event so the frontend can show it inline in the chat rather than leaving the request hanging. The OpenRouter client also retries once automatically on a transient 5xx from the provider before surfacing an error.

## Deployment

The frontend is deployed as a static Vite build (`chatbot-whyvineet.vercel.app`). Deploy the backend as a standard ASGI service (e.g. `uv run fastapi run main.py` in production mode) and point the frontend's `VITE_API_BASE_URL` at it.
