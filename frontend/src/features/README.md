# Frontend feature boundaries

The frontend is organized by user-facing feature instead of by implementation technology.

- `app-shell`: authenticated workspace layout, navigation, and tab routing.
- `dashboard`: learning workspace entry point.
- `chat`: intelligent tutoring chat and conversation tree UI.
- `practice`: exercise generation, grading, and wrong-question UI.
- `knowledge-map`: learner-facing knowledge graph/map UI.
- `admin-debug`: lower-priority management/debug surface.
- `knowledge-base`, `agent-flow`, `rag-process`: technical capabilities preserved behind `admin-debug`.

Shared code lives under `shared/`:

- `shared/lib`: API clients, auth helpers, error handling, and pure utilities.
- `shared/types`: cross-feature TypeScript types.
- `shared/contexts`: app-level React contexts.
- `shared/ui`: reusable UI primitives and icons.
