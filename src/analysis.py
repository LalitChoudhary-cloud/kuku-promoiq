"""
AI Analysis Engine for PromoIQ.
Evaluates screenplay units and segments across four core dimensions:
1. Hook Strength (0-3s high-impact visual/verbal trigger)
2. Cliffhanger Strength (unresolved cut, reveal, threat, question)
3. Standalone Context Clarity (viewer comprehension without prior lore)
4. Emotional Engagement (tension escalation, conflict density)
"""

import re
from typing import List, Tuple, Dict, Any, Optional
from src.models import ScreenplayUnit, UnitType, Segment

# High-impact linguistic and action lexicons for microdrama hooks and cliffhangers
SHOCK_KEYWORDS = {
    "betray", "betrayal", "traitor", "affair", "cheating", "mistress", "bastard",
    "kill", "murder", "poison", "dead", "die", "death", "blood", "gun", "knife",
    "marry", "wedding", "altar", "divorce", "ruin", "destroy", "disgrace", "shame",
    "pregnant", "baby", "secret", "lie", "liar", "fraud", "imposter", "duke",
    "cripple", "broken", "soldier", "slap", "stop", "never", "beg", "kneel",
    "mine", "leave", "abandon", "disown", "arrest", "confess", "truth", "money",
    "worthless", "garbage", "trash", "monster", "dare", "enough"
}

SUSPENSE_QUESTIONS = {
    "who are you", "what did you do", "is it true", "how could you",
    "why are you", "what do you mean", "where were you", "what is this",
    "are you out of your mind", "do you think you can", "who told you"
}

HIGH_TENSION_EMOTIONS = {
    "cold", "commanding", "furious", "desperate", "shaken", "heartbroken",
    "sneering", "mocking", "rage", "screaming", "trembling", "crying",
    "disdain", "merciless", "steely", "menacing", "whispering", "venomous",
    "bitter", "shocked", "terrified", "pleading", "smirking", "sharp"
}

VISUAL_HOOK_PATTERNS = [
    r"close-up", r"extreme close-up", r"snap zoom", r"gasps", r"slap",
    r"grabs", r"tears", r"trembling", r"shatters", r"draws a sword",
    r"confronts", r"kneels", r"pushes", r"steps in front", r"widens in bewilderment"
]


class SceneSemanticEngine:
    """
    Evaluates screenplay units and segment spans for dramatic effectiveness,
    calculating detailed sub-scores and semantic justifications.
    """

    def __init__(self):
        self.visual_hook_regex = re.compile("|".join(VISUAL_HOOK_PATTERNS), re.IGNORECASE)

    # -------------------------------------------------------------
    # 1. HOOK EVALUATION (First 3 Seconds of Candidate)
    # -------------------------------------------------------------
    def evaluate_hook(self, units: List[ScreenplayUnit], segment_start_sec: float) -> Tuple[float, str]:
        """
        Evaluates the opening 3 seconds of a candidate clip.
        Returns:
            (hook_score: float [0-100], hook_description: str)
        """
        if not units:
            return 0.0, "No units in segment."

        # Filter units that occur within the first 3.5 seconds of the segment start
        hook_window_end = segment_start_sec + 3.5
        hook_units = [u for u in units if u.start_sec <= hook_window_end]
        if not hook_units:
            hook_units = [units[0]]

        score = 30.0  # baseline
        reasons = []

        # Analyze dialogue, emotion, and actions in hook window
        has_speech = False
        for u in hook_units:
            # Check Dialogue
            if u.is_speech and u.text:
                has_speech = True
                text_lower = u.text.lower()
                
                # Check for high-impact questions
                if "?" in u.text:
                    score += 18.0
                    reasons.append("Suspenseful opening question")
                if "!" in u.text:
                    score += 10.0
                    reasons.append("High urgency/exclamation")

                # Keyword hits
                matched_keywords = [kw for kw in SHOCK_KEYWORDS if kw in text_lower]
                if matched_keywords:
                    score += min(25.0, len(matched_keywords) * 9.0)
                    reasons.append(f"Shock keyword '{matched_keywords[0]}'")

                # Emotion tag bonus
                if u.emotion:
                    emo_lower = u.emotion.lower()
                    if any(te in emo_lower for te in HIGH_TENSION_EMOTIONS):
                        score += 15.0
                        reasons.append(f"High-tension delivery ({u.emotion})")

            # Check Action / Visual Kinetic Energy
            elif u.is_action and u.text:
                text_lower = u.text.lower()
                if self.visual_hook_regex.search(text_lower):
                    score += 20.0
                    reasons.append("Kinetic dramatic action")
                if any(kw in text_lower for kw in ["slap", "shatter", "grabs", "tears", "faints", "gasps"]):
                    score += 25.0
                    reasons.append("High-arousal physical trigger")

            # Check Camera Framing
            elif u.is_camera and u.text:
                text_lower = u.text.lower()
                if "close-up" in text_lower or "extreme close-up" in text_lower:
                    score += 12.0
                    reasons.append("Intense close-up camera hook")
                elif "tracking" in text_lower or "pushes in" in text_lower:
                    score += 8.0

        # Cap score at 100
        final_score = min(100.0, max(15.0, score))
        desc = "; ".join(reasons) if reasons else "Moderate opening pacing"
        return round(final_score, 1), desc

    # -------------------------------------------------------------
    # 2. CLIFFHANGER EVALUATION (Final Cut Moment of Candidate)
    # -------------------------------------------------------------
    def evaluate_cliffhanger(self, units: List[ScreenplayUnit], segment_end_sec: float) -> Tuple[float, str]:
        """
        Evaluates whether the candidate cut point is an unresolved dramatic peak.
        Returns:
            (cliffhanger_score: float [0-100], cliffhanger_description: str)
        """
        if not units:
            return 0.0, "No units in segment."

        # The tail window is the final 4 seconds before the cut
        tail_window_start = max(segment_end_sec - 4.0, units[0].start_sec)
        tail_units = [u for u in units if u.end_sec >= tail_window_start]
        if not tail_units:
            tail_units = [units[-1]]

        score = 30.0  # baseline
        reasons = []

        last_unit = tail_units[-1]
        last_speech_unit = next((u for u in reversed(tail_units) if u.is_speech), None)

        if last_speech_unit and last_speech_unit.text:
            text = last_speech_unit.text.strip()
            text_lower = text.lower()

            # 1. Unanswered question at the cut
            if text.endswith("?"):
                score += 35.0
                reasons.append(f"Unanswered question ('{text[:35]}...')")
            elif "why" in text_lower or "who" in text_lower or "what" in text_lower:
                score += 20.0
                reasons.append("Suspenseful interrogative cliffhanger")

            # 2. Trailing off or ellipsis (interrupted thought / sudden cut)
            if text.endswith("...") or text.endswith("—") or text.endswith("-"):
                score += 25.0
                reasons.append("Sudden interrupted speech/revelation")

            # 3. High-stakes ultimatum / threat / shocking revelation
            matched_keywords = [kw for kw in SHOCK_KEYWORDS if kw in text_lower]
            if matched_keywords:
                score += min(25.0, len(matched_keywords) * 8.0)
                reasons.append(f"High-stakes reveal ending on '{matched_keywords[0]}'")

            # 4. Emotional escalation at cut
            if last_speech_unit.emotion:
                emo_lower = last_speech_unit.emotion.lower()
                if any(te in emo_lower for te in HIGH_TENSION_EMOTIONS):
                    score += 15.0
                    reasons.append(f"Cliffhanger delivered with {last_speech_unit.emotion}")

        # Check visual or action climax at cut
        for u in tail_units:
            if u.is_action and any(w in u.text.lower() for w in ["freezes", "stares", "gasp", "widens", "steps forward"]):
                score += 15.0
                reasons.append("Stunned visual reaction cut")
                break
            elif u.is_camera and "close-up" in u.text.lower():
                score += 10.0
                reasons.append("Dramatic close-up freeze-frame cut")
                break

        # Penalize if it cuts on an ordinary polite resolution (e.g., "Thank you", "Yes, mother")
        if last_speech_unit and last_speech_unit.text:
            tl = last_speech_unit.text.lower().strip()
            if tl in ["yes", "no", "thank you", "goodbye", "of course", "i understand"]:
                score -= 30.0
                reasons.append("Low-tension conclusive response (anti-cliffhanger)")

        final_score = min(100.0, max(10.0, score))
        desc = "; ".join(reasons) if reasons else "Standard narrative transition"
        return round(final_score, 1), desc

    # -------------------------------------------------------------
    # 3. STANDALONE CONTEXT EVALUATION (Comprehensibility)
    # -------------------------------------------------------------
    def evaluate_standalone_context(self, units: List[ScreenplayUnit], ep_number: int) -> Tuple[float, str]:
        """
        Determines whether a brand-new social media viewer can understand what is happening
        without needing lore or prior context.
        """
        if not units:
            return 0.0, "Empty segment."

        score = 65.0  # start at solid comprehensibility
        reasons = []

        dialogues = [u for u in units if u.is_speech and u.text]
        if not dialogues:
            return 40.0, "Segment contains no dialogue; purely visual action"

        first_speech = dialogues[0].text.strip()
        first_words = first_speech.lower().split()

        # Dangling Pronoun Penalty:
        # Starting with "He", "She", "They", "It", "That" without context is disorienting
        if first_words and first_words[0] in ["he", "she", "they", "it", "that", "him", "her"]:
            score -= 22.0
            reasons.append("Opens with ambiguous dangling pronoun")
        else:
            score += 10.0
            reasons.append("Clear opening reference")

        # Check if prominent characters or titles are named (Gerald, Juliana, Duke, Mother)
        all_text = " ".join(u.text for u in units)
        named_entities = ["juliana", "gerald", "clarissa", "alexander", "catherine", "duke", "mother", "father", "sister"]
        mentioned = [name for name in named_entities if name in all_text.lower()]
        if len(mentioned) >= 2:
            score += 15.0
            reasons.append(f"Identifies key conflict figures ({', '.join(mentioned[:3])})")
        elif len(mentioned) == 1:
            score += 8.0
            reasons.append(f"Clear reference to {mentioned[0]}")

        # Multi-speaker dynamic: promos with at least 2 interacting speakers are far clearer
        unique_speakers = {u.speaker for u in dialogues if u.speaker}
        if len(unique_speakers) >= 2:
            score += 15.0
            reasons.append(f"Direct interpersonal confrontation ({len(unique_speakers)} speakers)")
        elif len(unique_speakers) == 1:
            score -= 10.0
            reasons.append("Single-character monologue")

        final_score = min(100.0, max(20.0, score))
        desc = "; ".join(reasons) if reasons else "Self-contained dramatic scenario"
        return round(final_score, 1), desc

    # -------------------------------------------------------------
    # 4. EMOTIONAL ENGAGEMENT & TENSION ESCALATION
    # -------------------------------------------------------------
    def evaluate_emotional_engagement(self, units: List[ScreenplayUnit]) -> Tuple[float, str]:
        """
        Measures dramatic tension curve, emotional charge, and conflict density.
        """
        if not units:
            return 0.0, "Empty segment."

        score = 40.0
        reasons = []

        dialogues = [u for u in units if u.is_speech]
        actions = [u for u in units if u.is_action]

        # Emotion density in dialogue tags
        emotional_units = [u for u in dialogues if u.emotion and any(te in u.emotion.lower() for te in HIGH_TENSION_EMOTIONS)]
        if len(emotional_units) >= 3:
            score += 25.0
            reasons.append(f"High emotional intensity across {len(emotional_units)} exchanges")
        elif len(emotional_units) >= 1:
            score += 15.0
            reasons.append("Escalating emotional tension")

        # Conflict vocabulary density
        full_text_lower = " ".join(u.text.lower() for u in units)
        conflict_hits = sum(1 for kw in SHOCK_KEYWORDS if kw in full_text_lower)
        if conflict_hits >= 5:
            score += 20.0
            reasons.append(f"Dense dramatic stakes ({conflict_hits} conflict triggers)")
        elif conflict_hits >= 2:
            score += 10.0
            reasons.append("Contains active betrayal/romantic stakes")

        # Camera & visual pacing (healthy mix of close-ups and reaction shots)
        camera_units = [u for u in units if u.is_camera]
        if camera_units:
            close_ups = sum(1 for c in camera_units if "close-up" in c.text.lower())
            if close_ups >= 2:
                score += 12.0
                reasons.append("Tight visual pacing with reaction close-ups")

        final_score = min(100.0, max(20.0, score))
        desc = "; ".join(reasons) if reasons else "Consistent emotional dialogue"
        return round(final_score, 1), desc

