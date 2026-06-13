# Backend

FastAPI backend for authentication, chat streaming, RAG orchestration, question generation, grading, and learning/knowledge visualization APIs.

## Key paths

- `app/api/`: HTTP and SSE route handlers.
- `app/agents/`: LangGraph supervisor and specialist agents.
- `app/rag/`: retrieval, reranking, HyDE, semantic cache, and knowledge-graph helpers.
- `app/services/`: reusable business logic and stream helpers.
- `app/schemas/`: Pydantic request/response contracts.
- `tests/`: backend regression tests.

## Local commands

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m compileall app
```
