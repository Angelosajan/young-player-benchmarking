"""
Recruitment model - ball-progressing central midfielder (2015/16, four leagues).

Suitability: each of 15 per-90 metrics is turned into a percentile within the eligible pool,
metrics are averaged into 5 dimensions, and dimensions are combined with weights.

Similarity: how closely a player's statistical profile matches a chosen reference player
(cosine similarity of standardised metrics, shown as 0-100).

Run on its own to print the default shortlist:  python recruitment.py
"""

import numpy as np
import pandas as pd

from step2_metrics import LABELS

SEASON_FILE = "data/season_2015_16.csv"
ROLE = "Central midfield"
MIN_MINUTES = 900

# 15 metrics in 5 dimensions
DIMENSIONS = {
    "Progression": ["progressive_passes", "progressive_carries", "passes_final_third", "successful_dribbles"],
    "Ball security": ["pass_completion", "passes_completed", "ball_losses"],
    "Defensive work": ["tackles_interceptions", "ball_recoveries", "pressures"],
    "Chance creation": ["key_passes", "xa", "passes_into_box"],
    "Goal threat": ["np_xg", "shots"],
}
DEFAULT_WEIGHTS = {"Progression": 30, "Ball security": 20, "Defensive work": 25,
                   "Chance creation": 15, "Goal threat": 10}
LOWER_IS_BETTER = ["ball_losses"]
METRICS = [m for ms in DIMENSIONS.values() for m in ms]


def eligible_pool(season, min_minutes=MIN_MINUTES):
    """Central midfielders with enough league minutes, with percentiles within that pool."""
    pool = season[(season["primary_group"] == ROLE) & (season["minutes"] >= min_minutes)].copy()
    for m in METRICS:
        pool[f"{m}_pct"] = pool[m].rank(pct=True, ascending=m not in LOWER_IS_BETTER) * 100
    for dim, ms in DIMENSIONS.items():
        pool[dim] = pool[[f"{m}_pct" for m in ms]].mean(axis=1)
    return pool


def suitability(pool, weights):
    """Weighted average of the 5 dimension scores (0-100)."""
    total = sum(weights.values())
    if total == 0:
        return pd.Series(0.0, index=pool.index)
    return sum(pool[d] * w for d, w in weights.items()) / total


def similarity(pool, reference_id):
    """Cosine similarity (0-100) of each player's standardised profile to the reference player."""
    z = pool[METRICS].copy()
    for m in LOWER_IS_BETTER:
        z[m] = -z[m]
    z = (z - z.mean()) / z.std(ddof=0)
    ref = z[pool["player_id"] == reference_id].iloc[0].values
    cos = (z.values @ ref) / (np.linalg.norm(z.values, axis=1) * np.linalg.norm(ref))
    return pd.Series((cos + 1) / 2 * 100, index=pool.index)  # rescale -1..1 to 0..100


if __name__ == "__main__":
    season = pd.read_csv(SEASON_FILE)
    pool = eligible_pool(season)
    pool["suitability"] = suitability(pool, DEFAULT_WEIGHTS)
    top = pool.sort_values("suitability", ascending=False)
    print(f"{(season['primary_group'] == ROLE).sum()} central midfielders; "
          f"{len(pool)} eligible with {MIN_MINUTES}+ minutes")
    print(top[["player_name", "team", "league", "minutes", "suitability"] + list(DIMENSIONS)]
          .head(10).round(1).to_string(index=False))
