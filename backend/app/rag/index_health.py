from __future__ import annotations

import json

from app.rag.vectorstore import get_vector_store_manager


def collect_index_health() -> list[dict]:
    manager = get_vector_store_manager()
    return [manager.get_collection_info(name) for name in manager.list_collections()]


def main() -> None:
    print(json.dumps(collect_index_health(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
