"""
Scoring and ranking framework for PromoIQ.
Applies the explainable multi-factor scoring formula:
  Hook: 30%
  Cliffhanger: 30%
  Standalone Clarity: 20%
  Emotional Engagement: 15%
  Duration & Continuity: 5%
"""

from typing import List, Dict, Any, Optional
from src.models import ScoreBreakdown, PromoCandidate


class PromoScorer:
    """
    Computes explainable composite scores for promo candidates.
    Supports customizable weight profiles.
    """

    def __init__(
        self,
        weight_hook: float = 0.30,
        weight_cliffhanger: float = 0.30,
        weight_clarity: float = 0.20,
        weight_emotion: float = 0.15,
        weight_continuity: float = 0.05
    ):
        self.w_hook = weight_hook
        self.w_cliff = weight_cliffhanger
        self.w_clarity = weight_clarity
        self.w_emotion = weight_emotion
        self.w_continuity = weight_continuity

    def evaluate_duration_continuity(self, duration_sec: float, num_segments: int) -> float:
        """
        Optimal microdrama promo duration for TikTok/Reels is between 30s and 45s.
        Segments between 20-30s or 45-60s receive slightly lower duration scores.
        Penalizes excessive segment fragmentation.
        """
        if duration_sec < 20.0 or duration_sec > 60.0:
            return 0.0

        # Sweet spot score
        if 30.0 <= duration_sec <= 48.0:
            base = 100.0
        elif 25.0 <= duration_sec < 30.0 or 48.0 < duration_sec <= 55.0:
            base = 85.0
        else:
            base = 70.0

        # Penalty for too many cuts (viewer confusion on social)
        if num_segments == 1:
            segment_mod = 0.0
        elif num_segments == 2:
            segment_mod = -5.0
        else:
            segment_mod = -15.0

        return max(0.0, min(100.0, base + segment_mod))

    def calculate_score(
        self,
        hook_score: float,
        cliffhanger_score: float,
        clarity_score: float,
        emotion_score: float,
        duration_sec: float,
        num_segments: int = 1
    ) -> ScoreBreakdown:
        """Computes weighted composite score out of 100."""
        continuity_score = self.evaluate_duration_continuity(duration_sec, num_segments)

        composite = (
            (self.w_hook * hook_score) +
            (self.w_cliff * cliffhanger_score) +
            (self.w_clarity * clarity_score) +
            (self.w_emotion * emotion_score) +
            (self.w_continuity * continuity_score)
        )

        return ScoreBreakdown(
            hook_score=round(hook_score, 1),
            cliffhanger_score=round(cliffhanger_score, 1),
            clarity_score=round(clarity_score, 1),
            emotion_score=round(emotion_score, 1),
            continuity_score=round(continuity_score, 1),
            total_score=round(composite, 1)
        )

    def rank_candidates(self, candidates: List[PromoCandidate]) -> List[PromoCandidate]:
        """Sorts candidates by total_score descending and assigns rank numbers."""
        ranked = sorted(candidates, key=lambda c: c.scores.total_score, reverse=True)
        for i, cand in enumerate(ranked):
            cand.rank = i + 1
        return ranked

