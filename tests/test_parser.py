"""
Unit tests for screenplay parser and timestamp validator.
"""

import pytest
from src.parser import (
    parse_timestamp_to_seconds,
    format_seconds_to_timestamp,
    ScreenplayParser,
)
from src.models import UnitType


def test_timestamp_conversions():
    assert parse_timestamp_to_seconds("00:00.00") == 0.0
    assert parse_timestamp_to_seconds("01:23.45") == 83.45
    assert parse_timestamp_to_seconds("(02:18.00)") == 138.0
    assert parse_timestamp_to_seconds("01:02:03.00") == 3723.0

    assert format_seconds_to_timestamp(0.0) == "00:00.00"
    assert format_seconds_to_timestamp(83.45) == "01:23.45"
    assert format_seconds_to_timestamp(138.0) == "02:18.00"


def test_parser_sample_snippet():
    snippet = """EPISODE NUMBER: Episode 1
EPISODE LOGLINE: Lady Juliana arrives at the cathedral.
CONTINUITY NOTES: First episode.

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CATHEDRAL – DAY
Scene start: 00:00.00
Scene end: 02:18.00

Actions and dialogue:

**CAMERA:**
Start: (00:00.00) | End: (00:04.80)
Symmetrical framing on the heavy church doors.

**ACTION:**
Start: (00:01.00) | End: (00:04.80)
Juliana pauses at the threshold.

**MATRIARCH (Cold, Commanding):**
Start: (00:11.30) | End: (00:13.10)
"You should turn around, Juliana."
"""
    parser = ScreenplayParser()
    ep = parser.parse_text(snippet, filename="episode-001.txt")

    assert ep.episode_number == 1
    assert len(ep.scenes) == 1
    scene = ep.scenes[0]
    assert scene.heading == "INT. CATHEDRAL – DAY"
    assert scene.start_sec == 0.0
    assert scene.end_sec == 138.0
    assert len(scene.units) == 3

    u0 = scene.units[0]
    assert u0.unit_type == UnitType.CAMERA
    assert u0.duration_sec == 4.8

    u1 = scene.units[1]
    assert u1.unit_type == UnitType.ACTION

    u2 = scene.units[2]
    assert u2.unit_type == UnitType.DIALOGUE
    assert u2.speaker == "MATRIARCH"
    assert u2.emotion == "Cold, Commanding"
    assert u2.text == "You should turn around, Juliana."

