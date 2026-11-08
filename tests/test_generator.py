"""
Unit tests for candidate generator, duration limits, and scoring.
"""

import pytest
from src.parser import ScreenplayParser
from src.generator import CandidateGenerator
from src.scorer import PromoScorer
from src.evaluator import QualityChecker


SAMPLE_EP_TEXT = """EPISODE NUMBER: Episode 1
EPISODE LOGLINE: Lady Juliana arrives at the cathedral.
CONTINUITY NOTES: Test ep.

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CATHEDRAL – DAY
Scene start: 00:00.00
Scene end: 02:00.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:05.00)
Wide shot of cathedral doors opening.

**MATRIARCH (Cold, Commanding):**
Start: (00:05.00) | End: (00:10.00)
"You should turn around, Juliana. Gerald will never marry you!"

**LADY JULIANA (Heartbroken):**
Start: (00:10.00) | End: (00:18.00)
"Why? He swore he loved me! Why are you holding my sister's hand?"

**GERALD (Cruel, Sneering):**
Start: (00:18.00) | End: (00:26.00)
"Because Clarissa is worth ten of you. You are nothing but an embarrassment."

**LADY CLARISSA (Mocking):**
Start: (00:26.00) | End: (00:35.00)
"Did you really believe a broken girl like you could be a duchess?"

**LADY JULIANA (Desperate):**
Start: (00:35.00) | End: (00:44.00)
"How could you do this to me? Who planned this betrayal?"

**ACTION:**
Start: (00:44.00) | End: (00:48.00)
Gerald steps forward and shoves Juliana back into the rain.

**MATRIARCH (Merciless):**
Start: (00:48.00) | End: (00:54.00)
"Guard, throw her out before the Duke arrives!"

**CAMERA:**
Start: (00:54.00) | End: (00:58.00)
Extreme close-up on Juliana's tear-streaked face freezing in horror.
"""


def test_candidate_generation_and_duration_constraints():
    parser = ScreenplayParser()
    ep = parser.parse_text(SAMPLE_EP_TEXT)
    gen = CandidateGenerator()
    cands = gen.generate_single_segments(ep)

    assert len(cands) > 0
    for c in cands:
        # Every candidate must strictly satisfy 20-60s duration
        assert 20.0 <= c.total_duration_sec <= 60.0
        assert c.scores.total_score >= 50.0
        assert c.hook_text != ""
        assert c.cliffhanger_text != ""


def test_scorer_framework():
    scorer = PromoScorer()
    scores = scorer.calculate_score(
        hook_score=90.0,
        cliffhanger_score=85.0,
        clarity_score=80.0,
        emotion_score=75.0,
        duration_sec=35.0,
        num_segments=1
    )
    # Expected: 0.3*90 + 0.3*85 + 0.2*80 + 0.15*75 + 0.05*100
    # 27 + 25.5 + 16 + 11.25 + 5 = 84.75 -> 84.8
    assert abs(scores.total_score - 84.8) < 0.2
    assert scores.continuity_score == 100.0


def test_quality_checker_guardrails():
    checker = QualityChecker()
    parser = ScreenplayParser()
    ep = parser.parse_text(SAMPLE_EP_TEXT)
    gen = CandidateGenerator()
    cands = gen.generate_single_segments(ep)

    for c in cands:
        flags = checker.validate_candidate(c)
        # All generated candidates should pass duration and timestamp checks
        for f in flags:
            assert "FLAG_DURATION" not in f
            assert "FLAG_INVALID_TIMESTAMP" not in f

