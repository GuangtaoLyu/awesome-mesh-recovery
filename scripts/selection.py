# -*- coding: utf-8 -*-
"""Admission policy for literature discovery.

core: strict recovery/shape title phrases may be auto-indexed; borderline
      items enter a review queue.
embodied: relevant discoveries ALWAYS enter a review queue, never auto-publish
          into the curated hand/robot section.
"""
import re


def normalize_title(title):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def _has_phrase(title, phrases):
    norm = " " + normalize_title(title) + " "
    return any(" " + normalize_title(p) + " " in norm for p in phrases if normalize_title(p))


def decide(paper, config, track="core"):
    """Return (auto | review | ignore, reason).

    This gate applies only to newly discovered papers; it does not re-evaluate
    or remove earlier manually collected / published records.
    """
    title = paper.get("title") or ""
    if len(normalize_title(title)) < 14:
        return "ignore", "missing or implausibly short title"
    year = paper.get("year")
    if track == "embodied":
        if _has_phrase(title, config["selection"]["embodied_title_phrases"]):
            return "review", "robotics connection needs human scope/code verification"
        return "ignore", "no concrete recovery-to-robot connection in title"
    if track != "core":
        raise ValueError(f"Unknown discovery track: {track}")
    if _has_phrase(title, config["selection"]["auto_accept_title_phrases"]):
        if year:
            return "auto", "specific mesh / pose-and-shape recovery terminology"
        return "review", "strong title but publication year missing"
    if _has_phrase(title, config["selection"]["review_title_phrases"]):
        return "review", "possibly relevant recovery or hand-motion work"
    return "ignore", "outside the focused mesh/shape recovery title policy"
