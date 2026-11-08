"""
Pydantic data models for the PromoIQ Microdrama Promo Discovery System.
Defines strongly-typed representations of screenplays, timed units,
scenes, episodes, and promotional clip candidates.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UnitType(str, Enum):
    CAMERA = "CAMERA"
    ACTION = "ACTION"
    DIALOGUE = "DIALOGUE"
    SOUND_FX = "SOUND_FX"
    OTHER = "OTHER"


class ScreenplayUnit(BaseModel):
    """Represents a single atomic timed block in a screenplay (Camera, Action, or Dialogue)."""
    unit_id: str
    unit_type: UnitType
    speaker: Optional[str] = None
    emotion: Optional[str] = None
    text: str
    start_str: str
    end_str: str
    start_sec: float
    end_sec: float
    duration_sec: float

    @property
    def is_speech(self) -> bool:
        return self.unit_type == UnitType.DIALOGUE

    @property
    def is_action(self) -> bool:
        return self.unit_type == UnitType.ACTION

    @property
    def is_camera(self) -> bool:
        return self.unit_type == UnitType.CAMERA


class Scene(BaseModel):
    """Represents a scene within an episode."""
    scene_id: str
    scene_number: int
    heading: str
    start_str: str
    end_str: str
    start_sec: float
    end_sec: float
    duration_sec: float
    units: List[ScreenplayUnit] = Field(default_factory=list)


class Episode(BaseModel):
    """Represents a full parsed episode of a microdrama."""
    episode_id: str
    episode_number: int
    title: str
    logline: Optional[str] = None
    continuity_notes: Optional[str] = None
    scenes: List[Scene] = Field(default_factory=list)
    total_duration_sec: float = 0.0

    @property
    def all_units(self) -> List[ScreenplayUnit]:
        units = []
        for s in self.scenes:
            units.extend(s.units)
        return units


class Segment(BaseModel):
    """Represents a continuous segment within a promo clip."""
    episode_id: str
    episode_number: int
    start_str: str
    end_str: str
    start_sec: float
    end_sec: float
    duration_sec: float
    units: List[ScreenplayUnit] = Field(default_factory=list)
    scene_heading: Optional[str] = None


class ScoreBreakdown(BaseModel):
    """Explainable scoring breakdown based on the assignment framework."""
    hook_score: float = Field(..., ge=0, le=100, description="Hook strength (30% weight)")
    cliffhanger_score: float = Field(..., ge=0, le=100, description="Cliffhanger strength (30% weight)")
    clarity_score: float = Field(..., ge=0, le=100, description="Standalone clarity (20% weight)")
    emotion_score: float = Field(..., ge=0, le=100, description="Emotional engagement (15% weight)")
    continuity_score: float = Field(..., ge=0, le=100, description="Duration & pacing continuity (5% weight)")
    total_score: float = Field(..., ge=0, le=100, description="Weighted composite score out of 100")


class PromoCandidate(BaseModel):
    """Represents a promotional clip candidate."""
    promo_id: str
    promo_type: str = Field(..., description="single_segment, intra_episode_multi, or inter_episode_multi")
    episodes: List[int]
    segments: List[Segment]
    total_duration_sec: float
    hook_text: str
    cliffhanger_text: str
    why_it_works: str
    scores: ScoreBreakdown
    rank: Optional[int] = None
    quality_flags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

