# -*- coding: utf-8 -*-
"""Conservative automatic topic gate: method relevance, never venue prestige.

An arXiv preprint is eligible just like a conference paper. We use the TITLE
to establish the main contribution; abstracts can confirm a video-to-robot
pipeline but must not turn a passing related-work mention into admission.
"""
import re


def normalize_title(title):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).split())


def _has_phrase(text, phrases):
    normalized = " " + normalize_title(text) + " "
    return any(
        " " + normalize_title(p) + " " in normalized
        for p in phrases if normalize_title(p)
    )


def _matches(text, pattern):
    return bool(re.search(pattern, normalize_title(text)))


_BIOMEDICAL = re.compile(
    r"\b(dermis|dermal|fibroblast|collagen|bioprinting|"
    r"tissue engineering|cell derived|cartilage|skin graft)\b"
)
# HMR may be an off-the-shelf component in another task; that is not a new
# mesh-recovery method. Privacy-constrained *HMR itself* still qualifies.
_APPLICATION_ONLY = re.compile(
    r"\b(anonymization|anonymisation|face blurring|license plate)\b"
)


def decide(paper, config, track="core"):
    """Return (auto | ignore, reason); no acceptance or manual-review gate."""
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""
    norm = normalize_title(title)
    if len(norm) < 14:
        return "ignore", "missing or implausibly short title"

    if track == "core":
        if _BIOMEDICAL.search(norm):
            return "ignore", "biomedical mesh is not a human pose/shape model"
        if _APPLICATION_ONLY.search(norm):
            return "ignore", "uses mesh recovery for another primary task"
        if _has_phrase(title, config["selection"]["auto_accept_title_phrases"]):
            return "auto", "specific mesh or motion recovery title"
        # For newer terminology such as scene-human reconstruction, require
        # an actual *reconstruction/recovery* task in the title. The word
        # "mesh" by itself is not sufficient: a tissue-engineering mesh is
        # not a recovered human body surface.
        subject = _matches(title, r"\b(human|body|hand|hands|face|smpl|mano)\b")
        reconstruction = _matches(
            title, r"\b(recovery|reconstruction|reconstruct|"
                   r"pose and shape|shape estimation|motion capture)\b"
        )
        if subject and reconstruction:
            return "auto", "human/hand reconstruction title pattern"
        return "ignore", "outside human/hand recovery primary contributions"

    if track == "embodied":
        combined = title + " " + abstract
        # These tasks can mention retargeting as an application/background
        # without recovering any human motion or using human demonstrations.
        if _matches(
            title, r"\b(self other distinction|kinesthetic demonstrations|"
                   r"robot centric video synthesis)\b"
        ):
            return "ignore", "robotics method without human-video recovery bridge"
        robot = _matches(
            combined, r"\b(robot|robots|robotic|humanoid|dexterous|"
                      r"retargeting|teleoperation)\b"
        )
        human = _matches(
            combined, r"\b(human|hand|hands|body|video|monocular|"
                      r"egocentric|mocap|motion|demonstration)\b"
        )
        if not robot or not human:
            return "ignore", "no grounded human-to-robot connection"

        title_robot = _matches(title, r"\b(robot|robots|robotic|humanoid|dexterous)\b")
        direct_transfer = _matches(
            title, r"\b(human to robot|video to robot|vision to robot|"
                   r"robot from human|human video|human motion retargeting)\b"
        )
        transfer = _matches(title, r"\b(retarget|retargeting|teleoperation|"
                                  r"teleoperated|human imitation|visual imitation)\b")
        video_robot = title_robot and _matches(
            title, r"\b(video|monocular|egocentric|rgb|vision)\b"
        ) and _matches(
            combined, r"\b(human motion|human video|human demonstration|"
                          r"human pose|human body|video to robot|"
                          r"motion retargeting|imitation)\b"
        )
        imitation_tracking = title_robot and _matches(
            title, r"\b(imitation|mimic|human references|"
                   r"human demonstration|motion tracking)\b"
        ) and _matches(
            combined, r"\b(human|mocap|retargeted|video|demonstration)\b"
        )

        if direct_transfer or transfer or video_robot or imitation_tracking:
            return "auto", "explicit human motion to robot pipeline"
        return "ignore", "robotics/background match without primary recovery bridge"

    raise ValueError(f"Unknown discovery track: {track}")
