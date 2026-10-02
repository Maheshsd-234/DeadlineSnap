"""Test script to run live Gemini Vision extraction across the 3 fixture images."""

import json
import os
import sys
import toml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from generate_test_images import create_test_images
from extractor import extract_deadlines


def load_secrets():
    secrets_path = ".streamlit/secrets.toml"
    if os.path.exists(secrets_path):
        return toml.load(secrets_path)
    return {}


def main():
    secrets = load_secrets()
    api_key = secrets.get("GEMINI_API_KEY")
    model_name = secrets.get("GEMINI_MODEL", "gemini-2.5-flash")

    print(f"Testing with Gemini Model: {model_name}")
    print(f"API Key present: {bool(api_key and not api_key.startswith('your-'))}")

    fixtures = create_test_images("tests/fixtures")
    results = {}

    for name, path in fixtures.items():
        print(f"\n=======================================================")
        print(f"Testing Image: {name} ({path})")
        print(f"=======================================================")
        with open(path, "rb") as f:
            img_bytes = f.read()

        res = extract_deadlines(
            images=img_bytes,
            mime_types="image/png",
            api_key=api_key,
            model_name=model_name,
        )

        results[name] = res
        print(f"Status: {res.get('status')}")
        print(f"Reason: {res.get('reason')}")
        print(f"Extracted Count: {len(res.get('deadlines', []))}")
        print("Deadlines output preview:")
        print(json.dumps(res, indent=2))

    return results


if __name__ == "__main__":
    main()
