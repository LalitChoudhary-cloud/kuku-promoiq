"""
Candidate generation engine for PromoIQ.
Generates, filters, and deduplicates promotional clip candidates:
1. Single continuous segments (20.0s - 60.0s)
2. Intra-episode multi-segment montages
3. Cross-episode multi-segment story bridges
4. Non-Maximum Suppression (NMS) deduplication
"""

import math
from typing import List, Dict, Any, Optional
from src.models import (
    Episode,
    Scene,
    ScreenplayUnit,
    Segment,
    PromoCandidate,
    ScoreBreakdown
)
from src.parser import format_seconds_to_timestamp
from src.analysis import SceneSemanticEngine
from src.scorer import PromoScorer
from src.llm_provider import BaseLLMProvider, get_llm_provider


class CandidateGenerator:
    """
    Identifies high-potential promo intervals using sliding windows,
    scene boundary detection, and dynamic multi-segment stitching.
    """

    def __init__(
        self,
        semantic_engine: Optional[SceneSemanticEngine] = None,
        scorer: Optional[PromoScorer] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        min_duration: float = 20.0,
        max_duration: float = 60.0,
        nms_iou_threshold: float = 0.60
    ):
        self.engine = semantic_engine or SceneSemanticEngine()
        self.scorer = scorer or PromoScorer()
        self.llm = llm_provider or get_llm_provider()
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.nms_iou_threshold = nms_iou_threshold

    # -------------------------------------------------------------
    # 1. CONTINUOUS SINGLE-SEGMENT CANDIDATE GENERATION
    # -------------------------------------------------------------
    def generate_single_segments(self, episode: Episode) -> List[PromoCandidate]:
        """
        Discovers valid 20-60s continuous stretches within an episode.
        Prioritizes dialogue boundaries for natural speech cuts.
        """
        candidates: List[PromoCandidate] = []
        units = episode.all_units
        if not units:
            return candidates

        n = len(units)
        # Search every starting unit
        for i in range(n):
            u_start = units[i]
            # Fast-skip starting on purely technical camera instructions if next unit is dialogue/action
            # but allow camera if it defines the visual hook
            start_time = u_start.start_sec

            for j in range(i, n):
                u_end = units[j]
                end_time = u_end.end_sec
                duration = round(end_time - start_time, 2)

                if duration < self.min_duration:
                    continue
                if duration > self.max_duration:
                    break  # Window exceeded, stop inner loop

                # We have a valid window of 20-60s
                seg_units = units[i : j + 1]

                # Evaluate dimensions
                h_score, h_desc = self.engine.evaluate_hook(seg_units, start_time)
                # Quick prune if hook is extremely flat
                if h_score < 30.0:
                    continue

                c_score, c_desc = self.engine.evaluate_cliffhanger(seg_units, end_time)
                # Quick prune if cliffhanger is non-existent
                if c_score < 25.0:
                    continue

                clarity_score, cl_desc = self.engine.evaluate_standalone_context(seg_units, episode.episode_number)
                emotion_score, em_desc = self.engine.evaluate_emotional_engagement(seg_units)

                scores = self.scorer.calculate_score(
                    hook_score=h_score,
                    cliffhanger_score=c_score,
                    clarity_score=clarity_score,
                    emotion_score=emotion_score,
                    duration_sec=duration,
                    num_segments=1
                )

                # Only keep candidates with viable composite scores
                if scores.total_score >= 50.0:
                    seg = Segment(
                        episode_id=episode.episode_id,
                        episode_number=episode.episode_number,
                        start_str=format_seconds_to_timestamp(start_time),
                        end_str=format_seconds_to_timestamp(end_time),
                        start_sec=start_time,
                        end_sec=end_time,
                        duration_sec=duration,
                        units=seg_units
                    )
                    transcript_sample = " | ".join(
                        f"{u.speaker}: {u.text}" if u.speaker else u.text
                        for u in seg_units[:5]
                    )

                    why_works = self.llm.generate_explanation(
                        promo_type="Continuous Single-Segment",
                        hook_desc=h_desc,
                        cliffhanger_desc=c_desc,
                        context_desc=cl_desc,
                        transcript_sample=transcript_sample
                    )

                    promo = PromoCandidate(
                        promo_id=f"PROMO_EP{episode.episode_number:03d}_{len(candidates)+1:03d}",
                        promo_type="single_segment",
                        episodes=[episode.episode_number],
                        segments=[seg],
                        total_duration_sec=duration,
                        hook_text=h_desc,
                        cliffhanger_text=c_desc,
                        why_it_works=why_works,
                        scores=scores,
                        metadata={"start_sec": start_time, "end_sec": end_time}
                    )
                    candidates.append(promo)

        # Apply NMS to prune overlapping candidates from this episode
        return self._apply_nms(candidates)

    # -------------------------------------------------------------
    # 2. MULTI-SEGMENT INTRA-EPISODE MONTAGE GENERATION
    # -------------------------------------------------------------
    def generate_intra_episode_montage(self, episode: Episode) -> List[PromoCandidate]:
        """
        Creates a 2-segment montage from the same episode:
        Segment 1: High-impact opening hook (10s - 20s)
        Segment 2: Climax/cliffhanger confrontation (15s - 35s)
        Combined duration: 25s - 55s
        """
        candidates: List[PromoCandidate] = []
        units = episode.all_units
        if len(units) < 15:
            return candidates

        # Divide into early potential hooks and late potential cliffhangers
        split_idx = len(units) // 2
        early_units = units[:split_idx]
        late_units = units[split_idx:]

        # Find top hook segment
        best_hook_seg = None
        best_h_score = -1.0
        best_h_desc = ""

        for i in range(len(early_units)):
            for j in range(i + 2, min(i + 15, len(early_units))):
                dur = early_units[j].end_sec - early_units[i].start_sec
                if 10.0 <= dur <= 20.0:
                    sub = early_units[i : j + 1]
                    h_score, h_desc = self.engine.evaluate_hook(sub, early_units[i].start_sec)
                    if h_score > best_h_score:
                        best_h_score = h_score
                        best_h_desc = h_desc
                        best_hook_seg = (early_units[i].start_sec, early_units[j].end_sec, sub)

        if not best_hook_seg or best_h_score < 55.0:
            return candidates

        # Find top cliffhanger segment from second half
        best_cliff_seg = None
        best_c_score = -1.0
        best_c_desc = ""

        for i in range(len(late_units)):
            # Ensure the second segment starts strictly AFTER the first segment ends
            if late_units[i].start_sec <= best_hook_seg[1] + 0.5:
                continue

            for j in range(i + 2, len(late_units)):
                dur = late_units[j].end_sec - late_units[i].start_sec
                if 15.0 <= dur <= 30.0:
                    total_dur = best_hook_seg[1] - best_hook_seg[0] + dur
                    if self.min_duration <= total_dur <= self.max_duration:
                        sub = late_units[i : j + 1]
                        c_score, c_desc = self.engine.evaluate_cliffhanger(sub, late_units[j].end_sec)
                        if c_score > best_c_score:
                            best_c_score = c_score
                            best_c_desc = c_desc
                            best_cliff_seg = (late_units[i].start_sec, late_units[j].end_sec, sub, dur)

        if best_hook_seg and best_cliff_seg and best_c_score >= 55.0:
            total_duration = round((best_hook_seg[1] - best_hook_seg[0]) + best_cliff_seg[3], 2)
            all_montage_units = best_hook_seg[2] + best_cliff_seg[2]

            clarity_score, cl_desc = self.engine.evaluate_standalone_context(all_montage_units, episode.episode_number)
            emotion_score, em_desc = self.engine.evaluate_emotional_engagement(all_montage_units)

            scores = self.scorer.calculate_score(
                hook_score=best_h_score,
                cliffhanger_score=best_c_score,
                clarity_score=clarity_score,
                emotion_score=emotion_score,
                duration_sec=total_duration,
                num_segments=2
            )

            seg1 = Segment(
                episode_id=episode.episode_id,
                episode_number=episode.episode_number,
                start_str=format_seconds_to_timestamp(best_hook_seg[0]),
                end_str=format_seconds_to_timestamp(best_hook_seg[1]),
                start_sec=best_hook_seg[0],
                end_sec=best_hook_seg[1],
                duration_sec=round(best_hook_seg[1] - best_hook_seg[0], 2),
                units=best_hook_seg[2]
            )
            seg2 = Segment(
                episode_id=episode.episode_id,
                episode_number=episode.episode_number,
                start_str=format_seconds_to_timestamp(best_cliff_seg[0]),
                end_str=format_seconds_to_timestamp(best_cliff_seg[1]),
                start_sec=best_cliff_seg[0],
                end_sec=best_cliff_seg[1],
                duration_sec=round(best_cliff_seg[1] - best_cliff_seg[0], 2),
                units=best_cliff_seg[2]
            )

            why_works = (
                f"Two-part story teaser: Opens with '{best_h_desc}' before cutting directly to the episode's "
                f"unresolved climax ('{best_c_desc}'), eliminating filler to maximize retention."
            )

            promo = PromoCandidate(
                promo_id=f"PROMO_EP{episode.episode_number:03d}_MONTAGE",
                promo_type="intra_episode_multi",
                episodes=[episode.episode_number],
                segments=[seg1, seg2],
                total_duration_sec=total_duration,
                hook_text=best_h_desc,
                cliffhanger_text=best_c_desc,
                why_it_works=why_works,
                scores=scores,
                metadata={"type": "intra_episode_montage"}
            )
            candidates.append(promo)

        return candidates

    # -------------------------------------------------------------
    # 3. MULTI-SEGMENT CROSS-EPISODE BRIDGE GENERATION
    # -------------------------------------------------------------
    def generate_cross_episode_bridge(self, ep1: Episode, ep2: Episode) -> Optional[PromoCandidate]:
        """
        Creates a high-performing promo bridging two consecutive episodes:
        Segment 1: Cliffhanger from ep1 (12s - 25s)
        Segment 2: Shocking escalation/fallout from ep2 (12s - 25s)
        Combined duration: 25s - 50s
        """
        units1 = ep1.all_units
        units2 = ep2.all_units
        if not units1 or not units2:
            return None

        # Take tail of ep1
        tail_units = units1[-12:]
        if not tail_units:
            return None
        dur1 = tail_units[-1].end_sec - tail_units[0].start_sec
        if dur1 < 10.0 or dur1 > 28.0:
            # Adjust span to fit
            sub1 = [u for u in units1 if u.end_sec >= (ep1.total_duration_sec - 20.0)]
        else:
            sub1 = tail_units

        if not sub1:
            return None
        seg1_start = sub1[0].start_sec
        seg1_end = sub1[-1].end_sec
        seg1_dur = round(seg1_end - seg1_start, 2)

        # Take head of ep2
        sub2 = [u for u in units2 if u.end_sec <= 25.0]
        if not sub2:
            sub2 = units2[:10]
        seg2_start = sub2[0].start_sec
        seg2_end = sub2[-1].end_sec
        seg2_dur = round(seg2_end - seg2_start, 2)

        total_dur = round(seg1_dur + seg2_dur, 2)
        if total_dur < self.min_duration or total_dur > self.max_duration:
            return None

        # Evaluate combined units
        h_score, h_desc = self.engine.evaluate_hook(sub1, seg1_start)
        c_score, c_desc = self.engine.evaluate_cliffhanger(sub2, seg2_end)
        clarity_score, cl_desc = self.engine.evaluate_standalone_context(sub1 + sub2, ep1.episode_number)
        emotion_score, em_desc = self.engine.evaluate_emotional_engagement(sub1 + sub2)

        scores = self.scorer.calculate_score(
            hook_score=h_score,
            cliffhanger_score=c_score,
            clarity_score=clarity_score,
            emotion_score=emotion_score,
            duration_sec=total_dur,
            num_segments=2
        )

        if scores.total_score < 60.0:
            return None

        seg1 = Segment(
            episode_id=ep1.episode_id,
            episode_number=ep1.episode_number,
            start_str=format_seconds_to_timestamp(seg1_start),
            end_str=format_seconds_to_timestamp(seg1_end),
            start_sec=seg1_start,
            end_sec=seg1_end,
            duration_sec=seg1_dur,
            units=sub1
        )
        seg2 = Segment(
            episode_id=ep2.episode_id,
            episode_number=ep2.episode_number,
            start_str=format_seconds_to_timestamp(seg2_start),
            end_str=format_seconds_to_timestamp(seg2_end),
            start_sec=seg2_start,
            end_sec=seg2_end,
            duration_sec=seg2_dur,
            units=sub2
        )

        why_works = (
            f"Cross-episode cliffhanger bridge (Ep {ep1.episode_number} -> Ep {ep2.episode_number}): "
            f"Capitalizes on the climax of Ep {ep1.episode_number} and immediately showcases the shocking "
            f"consequences in Ep {ep2.episode_number}, driving binge-watching behavior."
        )

        return PromoCandidate(
            promo_id=f"PROMO_BRIDGE_EP{ep1.episode_number:02d}_EP{ep2.episode_number:02d}",
            promo_type="inter_episode_multi",
            episodes=[ep1.episode_number, ep2.episode_number],
            segments=[seg1, seg2],
            total_duration_sec=total_dur,
            hook_text=f"Ep {ep1.episode_number} Climax: {h_desc}",
            cliffhanger_text=f"Ep {ep2.episode_number} Escalation: {c_desc}",
            why_it_works=why_works,
            scores=scores,
            metadata={"bridge": f"{ep1.episode_number}->{ep2.episode_number}"}
        )

    # -------------------------------------------------------------
    # 4. NON-MAXIMUM SUPPRESSION (NMS) DEDUPLICATION
    # -------------------------------------------------------------
    def _apply_nms(self, candidates: List[PromoCandidate]) -> List[PromoCandidate]:
        """
        Deduplicates overlapping single-segment candidates from the same episode.
        Computes 1D Temporal Intersection over Union (IoU).
        If IoU > nms_iou_threshold, discards the lower-scoring candidate.
        """
        if not candidates:
            return []

        # Sort descending by total score
        sorted_cands = sorted(candidates, key=lambda c: c.scores.total_score, reverse=True)
        selected: List[PromoCandidate] = []

        for cand in sorted_cands:
            c_start = cand.metadata.get("start_sec", cand.segments[0].start_sec)
            c_end = cand.metadata.get("end_sec", cand.segments[0].end_sec)

            suppress = False
            for prev in selected:
                p_start = prev.metadata.get("start_sec", prev.segments[0].start_sec)
                p_end = prev.metadata.get("end_sec", prev.segments[0].end_sec)

                # Compute 1D temporal overlap
                inter_start = max(c_start, p_start)
                inter_end = min(c_end, p_end)
                intersection = max(0.0, inter_end - inter_start)

                union = (c_end - c_start) + (p_end - p_start) - intersection
                iou = intersection / union if union > 0 else 0.0

                if iou >= self.nms_iou_threshold:
                    suppress = True
                    break

            if not suppress:
                selected.append(cand)

        return selected
