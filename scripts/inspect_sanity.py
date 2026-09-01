"""One-off: dump the raw shape of genre / platform / region docs in Sanity.

Run: python scripts/inspect_sanity.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import config

for doc_type in ("genre", "platform", "region"):
    resp = requests.get(
        config.SANITY_QUERY_URL,
        params={"query": f'*[_type == "{doc_type}"][0...3]'},
        headers={"Authorization": f"Bearer {config.SANITY_TOKEN}"},
        timeout=30,
    )
    resp.raise_for_status()
    print(f"\n===== {doc_type} =====")
    print(json.dumps(resp.json().get("result", []), indent=2, ensure_ascii=False))
