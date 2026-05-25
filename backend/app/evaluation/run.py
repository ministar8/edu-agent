#!/usr/bin/env python3
"""评估体系 CLI 入口

    python -m app.evaluation.run --layer all
    python -m app.evaluation.run --layer ragas --category data_structure --limit 10
"""

from app.evaluation.cli import main

if __name__ == "__main__":
    main()
