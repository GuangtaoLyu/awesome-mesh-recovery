# -*- coding: utf-8 -*-
"""Title-first research-task assessment with abstract evidence for borderline work.

The admission decision is independent of conference acceptance or public code.
"verify" means *automatic metadata enrichment*, never human approval. Low-
evidence papers remain unpublished and are retried by future broad searches.
"""
import re


def normalize_title(value):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def _has(text, regex):
    return bool(re.search(regex, normalize_title(text)))


def _phrase(text, terms):
    norm = " " + normalize_title(text) + " "
    return any(" " + normalize_title(term) + " " in norm
               for term in terms if normalize_title(term))


_BIOMEDICAL = r"\b(dermis|dermal|fibroblast|collagen|bioprinting|tissue engineering|cell derived|skin graft)\b"
_APPLICATION = (
    r"\b(anonymization|anonymisation|license plate|face blurring|"
    r"camera pose estimation|camera network pose estimation|virtual object interaction|"
    r"interaction with virtual objects|generating multi view action data)\b"
)
_POSE_ONLY = r"\b(3d human pose estimation|2d pose estimation|human pose detection)\b"
_SHAPE_MESH = (
    r"\b(mesh recovery|mesh reconstruction|pose and shape|shape and pose|"
    r"shape estimation|human shape recovery|3d hand mesh|smpl parameter|"
    r"mano parameter|parametric human mesh)\b"
)
_SUBJECT = r"\b(human|humans|body|bodies|hand|hands|face|facial|smpl|mano|hmr)\b"
_RECOVERY = r"\b(recovery|recover|reconstruction|reconstruct|motion capture|mocap)\b"
_ABSTRACT_OUTPUT = (
    r"\b(smpl|smpl x|mano|parametric human|parametric body|"
    r"mesh vertices|human mesh|hand mesh|3d body shape|"
    r"3d human motion|3d hand motion|world space hand|"
    r"reconstructed human motion|hand object trajectories)\b"
)
_ABSTRACT_MAIN = (
    r"\b(we propose|we present|we introduce|this paper presents|"
    r"our method|our framework|we develop|we reconstruct|we estimate)\b"
)
_ROBOT_ONLY = (
    r"\b(self other distinction|kinesthetic demonstrations|"
    r"robot centric video synthesis|robot navigation|robot morphology optimization)\b"
)
_TRANSFER = (
    r"\b(human to robot|video to robot|vision to robot|"
    r"human motion retargeting|human motion transfer|"
    r"from human video|from human demonstrations|"
    r"from human references|human robot imitation)\b"
)
_ROBOT = r"\b(robot|robots|robotic|humanoid|dexterous|robot hand|retargeting|teleoperation)\b"
_HUMAN_REF = (
    r"\b(human motion|human video|human demonstrations?|human references?|"
    r"human pose|mocap|motion capture|retargeted human|"
    r"human hand|hand object interaction|egocentric hand)\b"
)
_EXECUTION = r"\b(retarget|retargeting|teleoperation|teleoperated|tracking|imitation|imitate|shadowing|robot control)\b"


def _result(decision, reason, evidence=(), score=0):
    return {"decision": decision, "reason": reason,
            "evidence": list(evidence), "score": score}


def assess(paper, config=None, track="core"):
    """Return an interpretable decision, evidence and *ordinal* evidence score.

    The score is not a calibrated statistical probability. Its purpose is to
    distinguish enough primary-task evidence from a mere keyword mention.
    """
    title = normalize_title(paper.get("title"))
    abstract = normalize_title(paper.get("abstract"))
    # Only the opening passage supplies positive "main task" evidence. A long
    # related-work citation late in the abstract should not admit a paper.
    opening = abstract[:650]
    if len(title) < 14:
        return _result("ignore", "missing or implausibly short title")

    if track == "core":
        if _has(title, _BIOMEDICAL):
            return _result("ignore", "biomedical mesh, not body pose/shape")
        if _has(title, _APPLICATION):
            return _result("ignore", "HMR is an application component")
        if _has(title, r"\b(shape correspondence|shape matching|point cloud registration)\b"):
            return _result("ignore", "shape correspondence, not recovery")
        if _has(title, _POSE_ONLY) and not _has(title, _SHAPE_MESH):
            # A standalone 3D pose estimator is not a mesh/shape estimator.
            return _result("ignore", "pose-only estimation")
        if _has(title, _SHAPE_MESH) and _has(title, _SUBJECT):
            return _result("auto", "explicit mesh/pose-and-shape research task",
                           ["title:mesh-or-shape", "title:human-or-hand"], 5)
        if (_has(title, r"\b(hand object|human|body|hand|face)\b") and _has(
            title, r"\b(motion recovery|motion reconstruction|mesh estimation|"
                   r"3d reconstruction|hand object reconstruction)\b"
        )) or (_has(title, r"\bhand object\b") and _has(
            title, r"\b(3d|4d|mesh|reconstruction)\b"
        )):
            return _result("auto", "explicit 3D human/hand motion reconstruction",
                           ["title:motion-recovery"], 5)
        if (_has(title, r"\b(mocap|motion capture)\b") and
                _has(opening, r"\b(human motion|3d human|3d body)\b") and
                _has(opening, _ABSTRACT_MAIN)):
            return _result("auto", "human motion capture confirmed by method abstract",
                           ["title:mocap", "abstract:human-3d-motion"], 4)
        title_subject = _has(title, _SUBJECT)
        title_task = _has(title, _RECOVERY)
        abstract_output = _has(opening, _ABSTRACT_OUTPUT)
        abstract_claim = _has(opening, _ABSTRACT_MAIN)
        if title_subject and title_task and abstract_output:
            return _result("auto", "recovery title confirmed by 3D output",
                           ["title:subject-and-recovery", "abstract:3d-output"], 4)
        if (title_subject and (title_task or _has(title, r"\b(pose|mesh|shape)\b"))):
            return _result("verify", "recovery task lacks specific shape/3D evidence",
                           ["title:plausible-recovery"], 2)
        if abstract_output and abstract_claim and _has(
            title, r"\b(hmr|smpl|reconstruction|human|hand|body)\b"
        ):
            return _result("verify", "abstract suggests recovery but title is broad",
                           ["abstract:task-evidence"], 2)
        return _result("ignore", "not primarily human/hand recovery")

    if track == "embodied":
        if _has(title, _ROBOT_ONLY):
            return _result("ignore", "robot-only task, not human-to-robot")
        if not _has(title + " " + abstract, _ROBOT):
            return _result("ignore", "no robot execution or retargeting")
        direct = _has(title, _TRANSFER)
        human = _has(title + " " + opening, _HUMAN_REF)
        execution = _has(title + " " + opening, _EXECUTION)
        title_transfer = _has(title, r"\b(retarget|retargeting|teleoperation|teleoperated)\b")
        title_robot = _has(title, r"\b(robot|humanoid|dexterous|robotic)\b")
        title_visual = _has(title, r"\b(video|monocular|visual|vision|rgb|egocentric)\b")
        title_tracker = _has(title, r"\b(tracking|imitation|shadowing|mimic|"
                                    r"human references?|human demonstrations?)\b")
        if direct and (human or execution or _has(title, r"\b(human|video|vision)\b")):
            return _result("auto", "explicit human/video-to-robot in title",
                           ["title:transfer", "human:reference"], 5)
        if title_transfer and human and execution:
            return _result("auto", "retargeting/teleoperation of human motion",
                           ["title:transfer", "abstract:human-reference"], 5)
        if title_robot and title_visual and human and execution:
            return _result("auto", "vision-conditioned robot execution of human motion",
                           ["title:video-and-robot", "abstract:human-motion"], 4)
        if title_robot and title_tracker and human and execution:
            return _result("auto", "robot tracking of human motion references",
                           ["title:tracking", "abstract:human-reference"], 4)
        if title_transfer or (title_robot and (title_visual or title_tracker)):
            return _result("verify", "robotics title, human reference not yet established",
                           ["title:possible-robot-bridge"], 2)
        return _result("ignore", "no primary human-motion-to-robot pipeline")

    raise ValueError(f"Unknown research track: {track}")


def decide(paper, config, track="core"):
    """Compatibility interface used by the existing pipeline/tests."""
    result = assess(paper, config, track)
    return result["decision"], result["reason"]
