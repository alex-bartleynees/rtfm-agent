# RTFM For Me

AI-powered documentation assistant using RAG (Retrieval-Augmented Generation). Ingest technical docs, ask questions, get answers — with semantic caching, session memory, and long-term user memory.

## Stack

| Layer | Technology |
|---|---|
| API | Python + FastAPI |
| LLM / Embeddings | Ollama (`llama3.2` + `nomic-embed-text`, 768d) |
| Vector store | PostgreSQL 17 + pgvector |
| Cache / Sessions | Redis 7 |
| Client | OpenAI-compatible (swap to Anthropic/OpenAI via env vars) |

## Architecture

```
Request
  └─► Semantic cache check (Redis)
        └─► Session history fetch (Redis, TTL-bound)
              └─► Vector search — doc chunks (pgvector)
                    └─► Memory search — long-term user memory (pgvector)
                          └─► LLM (Ollama / any OpenAI-compatible endpoint)
                                └─► Write cache + session (Redis)
                                      └─► Async memory extraction → Postgres
```

**Ingestion:** watched folder (`DOCS_DIR`) → chunk → embed → pgvector.

The folder watcher starts a background scan on startup, skips unchanged content,
and then queues individual changed files after one second without another event.
One worker processes the queue; failed files get two retries. File moves and
deletions are reconciled, including files removed while the app was offline.
Run a single API worker so only one ingestion worker watches the directory.
Progress and cumulative counters are available at `GET /ingestion/status`.

Configure exclusions in `.env` as a JSON array (restart after changes):

```dotenv
DOCS_IGNORE_PATTERNS='[".obsidian", ".git", ".trash", ".tmp-*", "*.tmp", "~*", "private", "drafts/*", "secret.md"]'
```

This replaces the defaults (the first six patterns above). Names without `/`
match files or directories at any depth. Patterns containing `/` match paths
relative to `DOCS_DIR`; `*` can span path separators. Matching a directory excludes
its descendants. Matching is case-sensitive; negation rules are not supported.
Ignored files are excluded from both startup scans and file events; previously
indexed files that become ignored are removed during startup reconciliation.

## Prerequisites

- [Nix](https://nixos.org/) with flakes enabled, **or** Python 3.12 + uv + docker-compose installed manually
- [Ollama](https://ollama.com/) running locally with the required models pulled

```sh
ollama pull llama3.2
ollama pull nomic-embed-text
```

## Setup

### 1. Enter the dev shell (Nix)

```sh
nix develop
```

This drops you into a shell with Python 3.12, uv, psql, redis-cli, docker-compose, and just.

### 2. Configure environment

```sh
cp .env.example .env   # then edit with your values
```

Required variables:

```
POSTGRES_PASSWORD=your_password
# Optional overrides (defaults shown):
POSTGRES_USER=postgres
OLLAMA_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.2
EMBED_MODEL=nomic-embed-text
DOCS_DIR=./docs
```

### 3. Start infrastructure

```sh
docker-compose up -d
```

### 4. Install Python dependencies

```sh
uv sync
```

### 5. Run database migrations

```sh
# Apply pgvector extension and schema
psql -h localhost -U postgres -d rag-ai -f schema.sql
```

### 6. Start the API

```sh
uvicorn app.main:app --reload
```

API available at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

## Common Commands

```sh
# Start/stop infrastructure
docker-compose up -d
docker-compose down

# Start API (dev, with reload)
uvicorn app.main:app --reload

# Ingest a document via API
curl -X POST http://localhost:8000/ingest/file \
  -F "file=@/path/to/doc.pdf"

# Health check
curl http://localhost:8000/health

# Connect to Postgres
psql -h localhost -U postgres -d rag-ai

# Connect to Redis
redis-cli

# Run tests
pytest

# Lint / format
ruff check .
ruff format .

# Install a new dependency
uv add <package>

# Update all dependencies
uv sync --upgrade
```

## Project Structure

```
app/
  main.py          # FastAPI app + routes
docker-compose.yml # Postgres + Redis
pyproject.toml     # Dependencies + build config
flake.nix          # Nix dev shell
```
