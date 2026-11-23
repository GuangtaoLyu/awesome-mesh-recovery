# -*- coding: utf-8 -*-
"""Automatic scope filter for core recovery and embodied follow-up papers.

Acceptance depends on task relevance, NOT conference decisions or code release.
Ambiguous papers are skipped for now and can be rediscovered in future runs.
Human review is optional correction through PRs, never a scheduled dependency.
"""
import re


def normalize_title(title):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def _has_phrase(text, phrases):
    normalized = " " + normalize_title(text) + " "
    return any(" " + normalize_title(p) + " " in normalized
               for p in phrases if normalize_title(p))


def _words(text, pattern):
    return bool(re.search(pattern, normalize_title(text)))


def decide(paper, config, track="core"):
    """Return (auto | ignore, reason); no manual-review gate.

    A preprint with an arXiv URL is a perfectly valid publication record.
    Only uncertain topic scope is excluded automatically.
    """
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""
    norm = normalize_title(title)
    if len(norm) < 14:
        return "ignore", "missing or implausibly short title"

    if track == "core":
        if _has_phrase(title, config["selection"]["auto_accept_title_phrases"]):
            return "auto", "specific human or hand recovery title"
        # Some newer work uses "motion reconstruction" rather than "mesh".
        subject = _words(title, r"\b(human|body|hand|face|smpl|mano)\b")
        reconstruction = _words(title, r"\b(recovery|reconstruction|mesh|pose and shape|motion capture)\b")
        if subject and reconstruction:
            # Generic 3D pose estimation and character animation alone are out
            # of scope unless explicit shape/mesh/recovery is present.
            return "auto", "recovery/reconstruction title pattern"
        return "ignore", "outside the focused recovery title scope"

    if track == "embodied":
        combined = title + " " + abstract
        robot = _words(combined, r"\b(robot|robots|robotic|humanoid|dexterous|teleoperation|"
                               r"retargeting|retarget|sim to real|sim2real)\b")
        human = _words(combined, r"\b(human|hand|hands|body|humanoid|video|videos|"
                               r"monocular|egocentric|motion|demonstration)\b")
        bridge = _words(combined, r"\b(reconstruction|recovery|retarget|retargeting|"
                                r"teleoperation|tracking|imitation|mimic|"
                                r"demonstration|hand object)\b")
        # An explicit title signal is necessary: an abstract passing mention
        # of robots must not turn every HMR paper into an embodied entry.
        title_signal = _has_phrase(title, config["selection"]["embodied_title_phrases"])
        if robot and human and bridge and title_signal:
            return "auto", "human/video/hand recovery connected to robot execution"
        return "ignore", "insufficient evidence of recovery-to-robot connection"

    raise ValueError(f"Unknown discovery track: {track}")
