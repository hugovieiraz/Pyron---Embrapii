"""Módulo de geometria projetiva e Single View Metrology (Criminisi et al.)."""

from src.geometry.vanishing_points import (
    LineSegment,
    VanishingPoint,
    VanishingGeometry,
    VanishingGeometryEstimator,
    VanishingPointEstimator,
)
from src.geometry.criminisi_metrology import (
    CriminisiMetrology,
    ProjectiveMetrologyEngine,
    ProjectiveDimensionsResult,
    ReferenceObject,
    VerticalMeasurement,
)

__all__ = [
    "LineSegment",
    "VanishingPoint",
    "VanishingGeometry",
    "VanishingGeometryEstimator",
    "VanishingPointEstimator",
    "CriminisiMetrology",
    "ProjectiveMetrologyEngine",
    "ProjectiveDimensionsResult",
    "ReferenceObject",
    "VerticalMeasurement",
]
