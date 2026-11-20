from collections import defaultdict
from dataclasses import dataclass

from plates.de_eu import normalize_edge_plate


@dataclass(frozen=True)
class FrameObservation:
    plate_text: str
    confidence: float
    sharpness_score: float = 1.0


@dataclass(frozen=True)
class VotedPlateResult:
    plate_raw: str
    plate_normalized: str
    plate_display: str
    confidence: float
    frame_count: int
    best_frame_index: int


class MultiFramePlateVoter:
    """
    Confidence + sharpness weighted multi-frame voting for ANPR tracks.
    Eliminates single-frame OCR misreads (e.g. O/0, B/8, I/1) as a vehicle crosses a lane.
    """

    def vote(self, observations: list[FrameObservation]) -> VotedPlateResult:
        if not observations:
            raise ValueError("At least one frame observation is required")

        # 1. Determine consensus length weighted by confidence * sharpness
        length_weights: dict[int, float] = defaultdict(float)
        normalized_obs: list[tuple[str, str, float, int]] = []
        for idx, obs in enumerate(observations):
            parsed = normalize_edge_plate(obs.plate_text)
            if not parsed.normalized:
                continue
            weight = max(0.05, obs.confidence) * max(0.1, obs.sharpness_score)
            length_weights[len(parsed.normalized)] += weight
            normalized_obs.append((parsed.normalized, parsed.display, weight, idx))

        if not normalized_obs:
            raise ValueError("No valid plate text found in observations")

        target_len = max(length_weights.items(), key=lambda kv: kv[1])[0]
        matching = [item for item in normalized_obs if len(item[0]) == target_len]

        # 2. Per-character weighted voting across matching-length reads
        voted_chars: list[str] = []
        for pos in range(target_len):
            char_scores: dict[str, float] = defaultdict(float)
            for norm_text, _disp, weight, _idx in matching:
                char_scores[norm_text[pos]] += weight
            best_char = max(char_scores.items(), key=lambda kv: kv[1])[0]
            voted_chars.append(best_char)

        consensus_norm = "".join(voted_chars)

        # Pick best representative frame matching consensus (or highest weight frame)
        best_idx = matching[0][3]
        best_weight = -1.0
        for norm_text, _disp, weight, idx in matching:
            bonus = 1.5 if norm_text == consensus_norm else 1.0
            if weight * bonus > best_weight:
                best_weight = weight * bonus
                best_idx = idx

        # Re-normalize through DE/EU formatter preserving spacing if an exact observation matched
        rep_raw = observations[best_idx].plate_text
        if normalize_edge_plate(rep_raw).normalized == consensus_norm:
            final_parsed = normalize_edge_plate(rep_raw)
        else:
            final_parsed = normalize_edge_plate(consensus_norm)

        avg_conf = sum(o.confidence for o in observations) / len(observations)
        # Boost slightly when multiple frames agree, capped at 0.995
        agreement_ratio = sum(1 for norm, *_ in matching if norm == consensus_norm) / len(observations)
        final_conf = min(0.995, round(avg_conf * (0.85 + 0.2 * agreement_ratio), 4))

        return VotedPlateResult(
            plate_raw=final_parsed.display,
            plate_normalized=final_parsed.normalized,
            plate_display=final_parsed.display,
            confidence=final_conf,
            frame_count=len(observations),
            best_frame_index=best_idx,
        )
