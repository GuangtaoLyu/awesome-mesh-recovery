# -*- coding: utf-8 -*-
"""Title-based classification for newly accepted human/hand recovery papers.

The human/hand recovery track is independent of video/scene input modality.
SMPL-X alone is not an "expressive hand/face" category; a temporal category
requires a temporal method, not merely frames from a camera.
"""
import re


def classify(paper, config=None):
    title = (paper.get("title") or "").lower()
    if re.search(r"\b(survey|systematic review|literature review|review of)\b", title):
        return "Surveys"
    if re.search(r"\b(dataset|benchmark|benchmarking|evaluation protocol)\b", title):
        return "Datasets & Benchmarks"
    if re.search(r"\b(hand|face|facial|expressive|mano)\b", title):
        return "Hand, Face & Expressive Mesh"
    if re.search(r"\b(occluded|occlusion|in.the.wild|partial visibility)\b", title):
        return "Occlusion & In-the-Wild Recovery"
    if re.search(
        r"\b(temporal|motion|sequence|online|streaming|dynamic|autoregressive|"
        r"spatio.temporal|video.based)\b", title,
    ):
        return "Motion & Temporal Recovery"
    return (config or {}).get("default_category", "Full-Body Human Mesh Recovery")
