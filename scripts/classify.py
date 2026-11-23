# -*- coding: utf-8 -*-
"""Conservative title-first categories for NEW automatically indexed papers.

Existing categories in data/papers.json are preserved. Embodied works have a
separate manually curated section and never become a robotics auto-category.
"""
import re


def classify(paper, config=None):
    title = (paper.get("title") or "").lower()
    if re.search(r"\b(survey|systematic review|literature review|review of)\b", title):
        return "Surveys"
    if re.search(r"\b(dataset|benchmark|benchmarking|evaluation protocol)\b", title):
        return "Datasets & Benchmarks"
    if re.search(r"\b(hand|face|facial|expressive|mano|smpl-x)\b", title):
        return "Hand, Face & Expressive Mesh"
    if re.search(r"\b(occluded|occlusion|in.the.wild|partial visibility)\b", title):
        return "Occlusion & In-the-Wild Recovery"
    if re.search(r"\b(video|videos|temporal|motion|sequence|online|streaming|dynamic)\b", title):
        return "Motion & Temporal Recovery"
    return (config or {}).get("default_category", "Full-Body Human Mesh Recovery")
