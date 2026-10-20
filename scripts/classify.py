# -*- coding: utf-8 -*-
"""Per-repo classifier for awesome-mesh-recovery.

Rule order matters (first match wins). Falls back to config default
(Full-Body Human Mesh Recovery).
"""
from lib_common import classify_by_rules

RULES = [
    ("Surveys", ["survey", "review of", "a review"]),
    ("Datasets & Benchmarks", ["dataset", "benchmark", "benchmarking"]),
    ("Hand, Face & Expressive Mesh",
     ["hand mesh", "face mesh", "expressive", "facial", "hand pose",
      "face reconstruction", "hand reconstruction", "hand-hoc", "face hoc"]),
    ("Occlusion & In-the-Wild Recovery",
     ["occlusion", "occluded", "in-the-wild", "in the wild", "real-world",
      "real world", "wild"]),
    ("Motion & Temporal Recovery",
     ["motion recovery", "motion ", "temporal", "video", "dynamic",
      "sequence", "autoregressive", "frame", "time-series", "spatio-temporal"]),
    ("Full-Body Human Mesh Recovery",
     ["mesh recovery", "human mesh", "pose and shape", "human shape",
      "body mesh", "pose estimation", "3d human", "hpe", "mesh from",
      "shape estimation", "parametric"]),
]

DEFAULT = "Full-Body Human Mesh Recovery"


def classify(paper, config=None):
    return classify_by_rules(paper, RULES, DEFAULT)
