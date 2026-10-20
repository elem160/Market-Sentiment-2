"""Export OpenAPI JSON schema with sorted keys to frontend/src/api/openapi.json."""
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app


def export_openapi() -> str:
    schema = app.openapi()
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "src", "api")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "openapi.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Exported OpenAPI schema to {output_path}")
    return output_path


if __name__ == "__main__":
    export_openapi()
