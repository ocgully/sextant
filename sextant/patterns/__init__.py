"""Design-pattern + anti-pattern detectors (§3B).

Each module exposes a single classifier class. Detectors run AFTER the
operation classifiers and may also run cross-file (shotgun-surgery).
"""
from sextant.patterns.strategy import StrategyPatternClassifier
from sextant.patterns.god_class import GodClassClassifier
from sextant.patterns.shotgun_surgery import detect_shotgun_surgery

__all__ = [
    "StrategyPatternClassifier",
    "GodClassClassifier",
    "detect_shotgun_surgery",
]
