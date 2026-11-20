"""
Step 2 - Per-90 metrics and positional percentiles.

Inputs (from step 1, plus the birth-date list):
  data/events.pkl, data/player_minutes.csv, data/u21_birthdates.csv
Output:
  data/player_metrics.csv  one row per outfield player with 180+ minutes:
                           per-90 metrics, percentile ranks within position group, U21 flag

Run:  python step2_metrics.py
"""

import numpy as np
import pandas as pd

MIN_MINUTES = 180            # below this, per-90 numbers are mostly noise
AGE_REFERENCE = "2024-07-01"  # ages are calculated at the mid-point of both tournaments
U21_MAX_AGE = 21

# Pitch is 120 x 80 (StatsBomb units, roughly yards); attacking towards x = 120
GOAL = np.array([120, 40])
SET_PIECES = ["Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"]
SUCCESS = ["Won", "Success In Play", "Success Out"]

# Metrics shown for each position group (radar + percentiles).
# Chosen to reflect what coaches typically ask of each role.
TEMPLATES = {
    "Centre-back": ["pass_completion", "progressive_passes", "passes_final_third", "progressive_carries",
                    "tackles_interceptions", "ball_recoveries", "clearances", "pressures"],
    "Full-back": ["progressive_passes", "progressive_carries", "passes_into_box", "key_passes",
                  "successful_dribbles", "tackles_interceptions", "pressures", "ball_recoveries"],
    "Central midfield": ["pass_completion", "passes_completed", "progressive_passes", "passes_final_third",
                         "progressive_carries", "tackles_interceptions", "pressures", "ball_recoveries"],
    "Attacking mid / winger": ["np_xg", "shots", "key_passes", "xa", "passes_into_box",
                               "successful_dribbles", "progressive_carries", "pressures"],
    "Striker": ["np_xg", "shots", "box_receptions", "key_passes", "xa",
                "successful_dribbles", "pressures", "ball_losses"],
}
LOWER_IS_BETTER = ["ball_losses"]

LABELS = {
    "pass_completion": "Pass completion %", "passes_completed": "Passes completed",
    "progressive_passes": "Progressive passes", "passes_final_third": "Passes into final third",
    "passes_into_box": "Passes into box", "key_passes": "Key passes", "xa": "Expected assists (xA)",
    "progressive_carries": "Progressive carries", "successful_dribbles": "Successful dribbles",
    "shots": "Shots", "np_xg": "Non-penalty xG", "box_receptions": "Receptions in box",
    "tackles_interceptions": "Tackles + interceptions won", "ball_recoveries": "Ball recoveries",
    "clearances": "Clearances", "pressures": "Pressures", "ball_losses": "Ball losses",
}


def xy(series):
    """Turn a column of [x, y] lists into an (n, 2) array (NaN where missing)."""
    return np.array([v if isinstance(v, list) else [np.nan, np.nan] for v in series], dtype=float)


def is_progressive(start, end):
    """
    Moves the ball substantially closer to goal. Threshold depends on where it happens:
    within own half 30 units, crossing halfway 15 units, within opposition half 10 units.
    """
    gain = np.linalg.norm(GOAL - start, axis=1) - np.linalg.norm(GOAL - end, axis=1)
    own_start, own_end = start[:, 0] < 60, end[:, 0] < 60
    needed = np.where(own_start & own_end, 30, np.where(own_start != own_end, 15, 10))
    return gain >= needed


def in_box(points):
    return (points[:, 0] >= 102) & (points[:, 1] >= 18) & (points[:, 1] <= 62)


def count_events(events):
    """Raw counts per player for every metric."""
    ev = events[events["period"] <= 4]  # drop penalty shoot-outs
    counts = pd.DataFrame(index=ev["player_id"].dropna().unique())

    # --- Passing ---
    passes = ev[ev["type"] == "Pass"]
    open_play = passes[~passes["pass_type"].isin(SET_PIECES)]
    completed = open_play[open_play["pass_outcome"].isna()]
    start, end = xy(completed["location"]), xy(completed["pass_end_location"])

    counts["passes_attempted"] = open_play.groupby("player_id").size()
    counts["passes_completed"] = completed.groupby("player_id").size()
    counts["progressive_passes"] = completed[is_progressive(start, end)].groupby("player_id").size()
    counts["passes_final_third"] = completed[(start[:, 0] < 80) & (end[:, 0] >= 80)].groupby("player_id").size()
    counts["passes_into_box"] = completed[~in_box(start) & in_box(end)].groupby("player_id").size()
    counts["key_passes"] = passes[(passes["pass_shot_assist"] == True) |
                                  (passes["pass_goal_assist"] == True)].groupby("player_id").size()

    # --- Shooting ---
    shots = ev[(ev["type"] == "Shot") & (ev["shot_type"] != "Penalty")]
    counts["shots"] = shots.groupby("player_id").size()
    counts["np_xg"] = shots.groupby("player_id")["shot_statsbomb_xg"].sum()

    # xA: xG of the shots each player's passes set up
    assisted = shots[shots["shot_key_pass_id"].notna()]
    shot_xg = assisted.groupby("shot_key_pass_id")["shot_statsbomb_xg"].sum()
    key = passes[passes["id"].isin(shot_xg.index)]
    counts["xa"] = key.assign(xg=key["id"].map(shot_xg)).groupby("player_id")["xg"].sum()

    receipts = ev[ev["type"] == "Ball Receipt*"]
    counts["box_receptions"] = receipts[in_box(xy(receipts["location"]))].groupby("player_id").size()

    # --- Carrying and dribbling ---
    carries = ev[ev["type"] == "Carry"]
    prog = is_progressive(xy(carries["location"]), xy(carries["carry_end_location"]))
    counts["progressive_carries"] = carries[prog].groupby("player_id").size()
    counts["successful_dribbles"] = ev[(ev["type"] == "Dribble") &
                                       (ev["dribble_outcome"] == "Complete")].groupby("player_id").size()
    counts["ball_losses"] = ev[ev["type"].isin(["Dispossessed", "Miscontrol"])].groupby("player_id").size()

    # --- Defending ---
    tackles = ev[(ev["type"] == "Duel") & (ev["duel_type"] == "Tackle") & ev["duel_outcome"].isin(SUCCESS)]
    interceptions = ev[(ev["type"] == "Interception") & ev["interception_outcome"].isin(SUCCESS)]
    counts["tackles_interceptions"] = (tackles.groupby("player_id").size()
                                       .add(interceptions.groupby("player_id").size(), fill_value=0))
    recoveries = ev[(ev["type"] == "Ball Recovery") & (ev["ball_recovery_recovery_failure"] != True)]
    counts["ball_recoveries"] = recoveries.groupby("player_id").size()
    counts["clearances"] = ev[ev["type"] == "Clearance"].groupby("player_id").size()
    counts["pressures"] = ev[ev["type"] == "Pressure"].groupby("player_id").size()

    return counts.fillna(0)


def main():
    events = pd.read_pickle("data/events.pkl")
    players = pd.read_csv("data/player_minutes.csv")
    births = pd.read_csv("data/u21_birthdates.csv")[["player_id", "dob"]]

    # Outfield players with enough minutes
    players = players[(players["minutes"] >= MIN_MINUTES) & (players["primary_group"] != "Goalkeeper")].copy()

    counts = count_events(events)
    df = players.merge(counts, left_on="player_id", right_index=True, how="left").fillna(0)

    # Pass completion is a percentage, so calculate it before converting counts to per-90 rates
    df["pass_completion"] = 100 * df["passes_completed"] / df["passes_attempted"].replace(0, np.nan)
    for col in [c for c in LABELS if c != "pass_completion"]:
        df[col] = df[col] / df["minutes"] * 90

    # Age and U21 flag (only U21 birth dates were collected; everyone else is a senior benchmark)
    df = df.merge(births, on="player_id", how="left")
    ref = pd.Timestamp(AGE_REFERENCE)
    df["age"] = ((ref - pd.to_datetime(df["dob"])).dt.days // 365.25).astype("Int64")
    df["is_u21"] = df["age"].notna() & (df["age"] <= U21_MAX_AGE)

    # Percentile rank within position group (0-100), against ALL ages
    for col in LABELS:
        # For "lower is better" metrics (ball losses) the fewest losses gets the highest percentile
        ascending = col not in LOWER_IS_BETTER
        df[f"{col}_pct"] = (df.groupby("primary_group")[col].rank(pct=True, ascending=ascending) * 100).round(0)

    df["group_size"] = df.groupby("primary_group")["player_id"].transform("count")
    df = df.drop(columns=["passes_attempted"]).round(2)
    df.to_csv("data/player_metrics.csv", index=False)

    print(f"Saved metrics for {len(df)} outfield players ({df['is_u21'].sum()} aged U21)")
    print(df.groupby("primary_group").agg(players=("player_id", "count"), u21=("is_u21", "sum")))


if __name__ == "__main__":
    main()
