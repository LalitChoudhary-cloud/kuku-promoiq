"""
Screenplay parser and timestamp validator for PromoIQ.
Parses formatted episode text files into structured Episode, Scene, and ScreenplayUnit models.
"""

import os
import re
from typing import List, Tuple, Optional
from src.models import Episode, Scene, ScreenplayUnit, UnitType


def parse_timestamp_to_seconds(ts_str: str) -> float:
    """
    Converts a timestamp string in formats like 'MM:SS.ms', '(MM:SS.ms)', or 'HH:MM:SS.ms'
    to float seconds.
    Example: '01:23.45' -> 83.45
    """
    cleaned = ts_str.strip().strip("()")
    parts = cleaned.split(":")
    
    if len(parts) == 2:
        minutes = float(parts[0])
        seconds = float(parts[1])
        return round(minutes * 60.0 + seconds, 3)
    elif len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        return round(hours * 3600.0 + minutes * 60.0 + seconds, 3)
    else:
        try:
            return round(float(cleaned), 3)
        except ValueError:
            raise ValueError(f"Unable to parse timestamp: '{ts_str}'")


def format_seconds_to_timestamp(seconds: float) -> str:
    """
    Converts seconds float to standardized 'MM:SS.ms' format.
    Example: 83.45 -> '01:23.45'
    """
    if seconds < 0:
        seconds = 0.0
    minutes = int(seconds // 60)
    rem_seconds = seconds - (minutes * 60)
    return f"{minutes:02d}:{rem_seconds:05.2f}"


class ScreenplayParser:
    """
    Robust state-machine parser for Kuku microdrama screenplays.
    Handles metadata, scenes, dialogue with emotion annotations, camera, and actions.
    """

    def __init__(self):
        self.header_re = re.compile(r"^\*\*([^*]+)\*\*", re.MULTILINE)
        self.time_re = re.compile(
            r"Start:\s*\(([0-9:.]+)\)\s*\|\s*End:\s*\(([0-9:.]+)\)", re.IGNORECASE
        )
        self.scene_start_re = re.compile(
            r"Scene start:\s*([0-9:.]+)", re.IGNORECASE
        )
        self.scene_end_re = re.compile(
            r"Scene end:\s*([0-9:.]+)", re.IGNORECASE
        )
        self.scene_heading_re = re.compile(
            r"Scene heading:\s*(.+)", re.IGNORECASE
        )

    def parse_file(self, file_path: str) -> Episode:
        """Parses a single screenplay file from disk."""
        filename = os.path.basename(file_path)
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return self.parse_text(content, filename=filename)

    def parse_text(self, text: str, filename: str = "unknown") -> Episode:
        """Parses screenplay text into an Episode instance."""
        # 1. Extract Episode Metadata
        ep_num = self._extract_episode_number(text, filename)
        logline = self._extract_regex(text, r"EPISODE LOGLINE:\s*(.+)")
        continuity = self._extract_regex(text, r"CONTINUITY NOTES:\s*(.+)")
        
        # 2. Split scenes
        # Screenplays delineate scenes with "SCENE XX"
        scene_splits = re.split(r"(?m)^SCENE\s+(\d+)", text)
        
        scenes: List[Scene] = []
        if len(scene_splits) > 1:
            # scene_splits[0] is preamble before SCENE 01
            for i in range(1, len(scene_splits), 2):
                sc_num_str = scene_splits[i]
                sc_body = scene_splits[i + 1] if i + 1 < len(scene_splits) else ""
                scene = self._parse_scene(int(sc_num_str), sc_body, ep_num)
                if scene:
                    scenes.append(scene)
        else:
            # Fallback if no SCENE header is found
            scene = self._parse_scene(1, text, ep_num)
            if scene:
                scenes.append(scene)

        # 3. Compute episode total duration
        total_duration = 0.0
        if scenes:
            total_duration = max(s.end_sec for s in scenes)

        return Episode(
            episode_id=f"EP_{ep_num:03d}",
            episode_number=ep_num,
            title=f"Episode {ep_num}",
            logline=logline,
            continuity_notes=continuity,
            scenes=scenes,
            total_duration_sec=total_duration
        )

    def _extract_episode_number(self, text: str, filename: str) -> int:
        match = re.search(r"EPISODE NUMBER:\s*(?:Episode\s*)?(\d+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        file_match = re.search(r"episode-?(\d+)", filename, re.IGNORECASE)
        if file_match:
            return int(file_match.group(1))
        return 1

    def _extract_regex(self, text: str, pattern: str) -> Optional[str]:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else None

    def _parse_scene(self, scene_number: int, scene_text: str, ep_num: int) -> Optional[Scene]:
        heading_m = self.scene_heading_re.search(scene_text)
        heading = heading_m.group(1).strip() if heading_m else f"SCENE {scene_number:02d}"
        
        start_m = self.scene_start_re.search(scene_text)
        end_m = self.scene_end_re.search(scene_text)
        
        start_str = start_m.group(1).strip() if start_m else "00:00.00"
        end_str = end_m.group(1).strip() if end_m else "00:00.00"
        
        start_sec = parse_timestamp_to_seconds(start_str)
        end_sec = parse_timestamp_to_seconds(end_str)
        
        # Parse blocks / units inside this scene
        units = self._parse_units(scene_text, ep_num, scene_number)
        
        # If scene end_sec was 0, infer from units
        if end_sec <= start_sec and units:
            start_sec = min(u.start_sec for u in units)
            end_sec = max(u.end_sec for u in units)
            start_str = format_seconds_to_timestamp(start_sec)
            end_str = format_seconds_to_timestamp(end_sec)

        duration = max(0.0, end_sec - start_sec)

        return Scene(
            scene_id=f"EP{ep_num:03d}_SC{scene_number:02d}",
            scene_number=scene_number,
            heading=heading,
            start_str=start_str,
            end_str=end_str,
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=duration,
            units=units
        )

    def _parse_units(self, scene_text: str, ep_num: int, scene_number: int) -> List[ScreenplayUnit]:
        """
        Extracts each **TAG:** block, its Start/End timestamps, and its body text.
        """
        units: List[ScreenplayUnit] = []
        
        # Match pattern: **HEADER:** or **HEADER**: \n Start: (X) | End: (Y) \n BODY
        block_pattern = re.compile(
            r"^\*\*([^*]+?):?\*\*:?\s*\n"
            r"Start:\s*\(([0-9:.]+)\)\s*\|\s*End:\s*\(([0-9:.]+)\)\s*\n"
            r"(.*?)(?=(?:^\*\*[^*]+:?\*\*:?\s*\n|Scene start:|Scene end:|SCENE\s+\d+|\Z))",
            re.MULTILINE | re.DOTALL
        )

        matches = list(block_pattern.finditer(scene_text))
        
        for idx, m in enumerate(matches):
            raw_header = m.group(1).strip()
            # strip any trailing colon that was captured
            if raw_header.endswith(":"):
                raw_header = raw_header[:-1].strip()

            start_str = m.group(2).strip()
            end_str = m.group(3).strip()
            body_text = m.group(4).strip()
            
            start_sec = parse_timestamp_to_seconds(start_str)
            end_sec = parse_timestamp_to_seconds(end_str)
            
            # Validation: ensure end >= start
            if end_sec < start_sec:
                end_sec = start_sec

            duration_sec = round(end_sec - start_sec, 3)

            # Determine Unit Type, Speaker, Emotion
            unit_type, speaker, emotion = self._categorize_header(raw_header)

            # Clean body text
            body_text = body_text.strip().strip('"').strip()

            unit = ScreenplayUnit(
                unit_id=f"EP{ep_num:03d}_SC{scene_number:02d}_U{idx+1:03d}",
                unit_type=unit_type,
                speaker=speaker,
                emotion=emotion,
                text=body_text,
                start_str=start_str,
                end_str=end_str,
                start_sec=start_sec,
                end_sec=end_sec,
                duration_sec=duration_sec
            )
            units.append(unit)

        return units

    def _categorize_header(self, header: str) -> Tuple[UnitType, Optional[str], Optional[str]]:
        """Parses headers like CAMERA, ACTION, or CHARACTER (Emotion)."""
        upper = header.upper().strip()
        if upper.startswith("CAMERA"):
            return UnitType.CAMERA, None, None
        if upper.startswith("ACTION"):
            return UnitType.ACTION, None, None
        if upper.startswith("SOUND"):
            return UnitType.SOUND_FX, None, None

        # Check for dialogue with emotion: "MATRIARCH (Cold, Commanding)"
        match = re.search(r"^([^(]+)(?:\(([^)]+)\))?", header)
        if match:
            speaker = match.group(1).strip()
            emotion = match.group(2).strip() if match.group(2) else None
            return UnitType.DIALOGUE, speaker, emotion

        return UnitType.OTHER, header.strip(), None


def parse_all_episodes(directory_path: str) -> List[Episode]:
    """Helper to parse all screenplay files in a directory in sorted order."""
    parser = ScreenplayParser()
    episodes: List[Episode] = []
    
    files = sorted([f for f in os.listdir(directory_path) if f.endswith(".txt")])
    for f in files:
        full_path = os.path.join(directory_path, f)
        ep = parser.parse_file(full_path)
        episodes.append(ep)
        
    episodes.sort(key=lambda x: x.episode_number)
    return episodes
