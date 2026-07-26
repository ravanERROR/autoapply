"""Seed default filter profiles."""
import json, os
from pathlib import Path

DEFAULTS = {
    "linkedin.json": {"name": "linkedin_default", "platform": "linkedin", "keywords": ["software engineer"], "locations": ["Remote"], "experienceMin": 0, "experienceMax": 5},
    "naukri.json": {"name": "naukri_default", "platform": "naukri", "keywords": ["software engineer"], "locations": ["Bangalore"], "experienceMin": 0, "experienceMax": 5},
    "indeed.json": {"name": "indeed_default", "platform": "indeed", "keywords": ["software engineer"], "locations": ["United States"], "experienceMin": 0, "experienceMax": 10},
}
dir_ = Path(__file__).parent.parent / "configs" / "filters"
dir_.mkdir(parents=True, exist_ok=True)
for name, data in DEFAULTS.items():
    p = dir_ / name
    if not p.exists():
        p.write_text(json.dumps(data, indent=2))
        print(f"Created {p}")
    else:
        print(f"Skip {p}")
