"""Write the OpenAPI schema to openapi.json.

Creating the app does not open a database connection. If DATABASE_URL is unset, a
placeholder is used so this can run without a real database.
"""

import json
import os
from pathlib import Path

_PLACEHOLDER_DATABASE_URL = "postgresql://placeholder:placeholder@127.0.0.1:5432/placeholder"


def openapi_path() -> Path:
    return Path(__file__).resolve().parents[1] / "openapi.json"


def export_openapi() -> None:
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = _PLACEHOLDER_DATABASE_URL
    # Imported after the placeholder is set. Importing the package does not read settings.
    from dentacircle.main import create_app

    schema = create_app().openapi()
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    openapi_path().write_text(text)


if __name__ == "__main__":
    export_openapi()
