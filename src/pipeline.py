"""
Pipeline orchestration engine for PromoIQ.
Processes all screenplay episodes, discovers candidates, scores, ranks,
validates quality, and exports raw CSV and JSON deliverables.
"""

import os
import json
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from src.parser import parse_all_episodes
from src.generator import CandidateGenerator
from src.scorer import PromoScorer
from src.evaluator import QualityChecker, BenchmarkEvaluator
from src.models import PromoCandidate, Episode


class PromoIQPipeline:
    """End-to-end processing pipeline for microdrama promotional discovery."""

    def __init__(
        self,
        dataset_dir: str,
        output_dir: str = "outputs",
        min_duration: float = 20.0,
        max_duration: float = 60.0
    ):
        self.dataset_dir = dataset_dir
        self.output_dir = output_dir
        self.generator = CandidateGenerator(min_duration=min_duration, max_duration=max_duration)
        self.scorer = PromoScorer()
        self.checker = QualityChecker()
        os.makedirs(output_dir, exist_ok=True)

    def run(self, max_episodes: Optional[int] = None) -> List[PromoCandidate]:
        """Runs candidate discovery, scoring, and ranking across the dataset."""
        print(f"[PromoIQ] Ingesting screenplays from: {self.dataset_dir}")
        episodes = parse_all_episodes(self.dataset_dir)
        if max_episodes:
            episodes = episodes[:max_episodes]

        print(f"[PromoIQ] Parsed {len(episodes)} episodes successfully.")

        all_candidates: List[PromoCandidate] = []

        # 1. Single continuous & intra-episode montages
        for idx, ep in enumerate(episodes):
            single_cands = self.generator.generate_single_segments(ep)
            all_candidates.extend(single_cands)

            intra_montages = self.generator.generate_intra_episode_montage(ep)
            all_candidates.extend(intra_montages)

        # 2. Cross-episode story bridges
        for i in range(len(episodes) - 1):
            bridge = self.generator.generate_cross_episode_bridge(episodes[i], episodes[i + 1])
            if bridge:
                all_candidates.append(bridge)

        print(f"[PromoIQ] Total raw candidate pool: {len(all_candidates)}")

        # 3. Quality assurance & flag assignment
        for cand in all_candidates:
            self.checker.validate_candidate(cand)

        # 4. Rank candidates by composite score
        ranked = self.scorer.rank_candidates(all_candidates)
        print(f"[PromoIQ] Ranked top {len(ranked)} promotional candidates.")

        return ranked

    def export_results(self, candidates: List[PromoCandidate]) -> Tuple[str, str]:
        """Exports candidates to raw JSON and CSV files."""
        json_path = os.path.join(self.output_dir, "promos_discovered.json")
        csv_path = os.path.join(self.output_dir, "promos_discovered.csv")

        # Prepare JSON payload
        json_data = [cand.model_dump() for cand in candidates]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        # Prepare CSV rows
        rows = []
        for c in candidates:
            # Segment summary
            seg_details = []
            for s in c.segments:
                seg_details.append(f"Ep {s.episode_number} [{s.start_str} - {s.end_str}] ({s.duration_sec}s)")
            segment_str = " + ".join(seg_details)

            first_seg = c.segments[0]
            last_seg = c.segments[-1]

            rows.append({
                "Rank": c.rank,
                "Promo ID": c.promo_id,
                "Promo Type": c.promo_type,
                "Episodes": ", ".join(str(e) for e in c.episodes),
                "Start Timestamp": first_seg.start_str,
                "End Timestamp": last_seg.end_str,
                "Total Duration (s)": c.total_duration_sec,
                "Segment Breakdown": segment_str,
                "Total Score (/100)": c.scores.total_score,
                "Hook Score (30%)": c.scores.hook_score,
                "Cliffhanger Score (30%)": c.scores.cliffhanger_score,
                "Standalone Clarity (20%)": c.scores.clarity_score,
                "Emotional Engagement (15%)": c.scores.emotion_score,
                "Duration & Continuity (5%)": c.scores.continuity_score,
                "Hook Description": c.hook_text,
                "Cliffhanger Description": c.cliffhanger_text,
                "Why Promo Works": c.why_it_works,
                "Quality Flags": "; ".join(c.quality_flags) if c.quality_flags else "Clean"
            })

        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False, encoding="utf-8")

        print(f"[PromoIQ] Exported JSON to: {json_path}")
        print(f"[PromoIQ] Exported CSV to: {csv_path}")

        return json_path, csv_path


if __name__ == "__main__":
    from typing import Tuple
    pipeline = PromoIQPipeline(dataset_dir="dataset/I Married a Broken Soldier. He was a Duke")
    cands = pipeline.run()
    pipeline.export_results(cands)
