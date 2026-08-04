"""Export Jarvis's OpenAPI schema to a committed JSON file (Phase 21).

FastAPI already serves this live at /openapi.json (and a browsable
Swagger UI at /docs) for any running instance — this script exists so
"generate API documentation" also produces a durable, diffable
artifact that doesn't require a running server or a database/plugin
setup to inspect: `create_app()` only needs a ServiceContainer with a
`Settings` instance registered, not the full bootstrap() sequence.

Usage: python scripts/export_openapi.py [output_path]
(default output_path: docs/openapi.json)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jarvis.api.app import create_app  # noqa: E402
from jarvis.core.config import Settings  # noqa: E402
from jarvis.core.container import ServiceContainer  # noqa: E402


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/openapi.json")

    container = ServiceContainer()
    container.register_instance(Settings, Settings())
    app = create_app(container)

    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema ({len(schema.get('paths', {}))} paths) to {output_path}")


if __name__ == "__main__":
    main()
