---
name: testing-frontend-navigation
description: Test the Edu Agent frontend navigation and information architecture flows end-to-end. Use when verifying changes to the app shell, dashboard actions, tab routing, or management/debug views.
---

# Testing Edu Agent frontend navigation

## Devin Secrets Needed

- None for navigation-only testing with local data.
- Optional for deeper AI/RAG generation tests: `LLM_API_KEY`.
- Optional for full knowledge graph data tests: `NEO4J_PASSWORD` if the Neo4j instance requires authentication.

## Local setup

1. Start the backend from `backend/` with a local-only JWT secret:
   ```powershell
   $env:JWT_SECRET='test-secret'
   $env:LLM_API_KEY='test-key'
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Start the frontend from `frontend/`:
   ```powershell
   npm run dev
   ```
3. Open the frontend using `http://localhost:3000`, not `http://127.0.0.1:3000`. The default backend CORS origin allows `http://localhost:3000`.
4. For a local test session, register or log in as a student. The local registration endpoint can create a disposable account; do not use production credentials for navigation-only tests.

## Core navigation assertions

- Refreshing `/` as an authenticated student should land on the learning workspace/dashboard.
- The top-level nav should be learning-first. Verify the primary learning entries and the lower-priority management/debug entry.
- Dashboard action cards should route to the intended pages:
  - practice action opens the practice/questions panel and should prefill a topic when one is provided.
  - chat action opens the chat panel and should prefill the question input.
  - knowledge-map action opens the knowledge map and should preserve focused-topic context when provided.
- Technical views that are intentionally downgraded should remain accessible from management/debug instead of top-level navigation.

## Notes and common pitfalls

- A missing local Neo4j service may cause the knowledge map to show an empty-state card. For navigation tests, this is acceptable if the knowledge-map page and focus banner are visible. For graph-data tests, start Neo4j and seed/import graph data first.
- Use browser/desktop recording for UI navigation tests and annotate the default state, each routing action, and any preserved debug views.
- After the UI flow, inspect the browser console. React DevTools and Fast Refresh informational logs are expected in development mode; runtime errors are not.
