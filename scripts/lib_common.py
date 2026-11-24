# -*- coding: utf-8 -*-
"""Small shared helpers for the automatic paper index."""
import json
import os
import re


def norm_title(title):
    """Normalize English paper titles for title/ID deduplication."""
    if not title:
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(title).lower()).split())


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as file:
        return json.load(file)
