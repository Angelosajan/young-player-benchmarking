"""
Step 3 - Season data for the recruitment analysis.

Downloads StatsBomb open data for the 2015/16 Premier League, La Liga, Serie A and Ligue 1
(about 1,500 matches) and builds one row per player with minutes, primary position group
and per-90 metrics.

To keep memory low, each match is summarised as soon as it is downloaded (we never hold
all ~5 million events at once). Progress is saved every 50 matches, so if the download
is interrupted, running the script again continues where it stopped.

Output:  data/season_2015_16.csv
Run:     python step3_recruitment_data.py      (about 40-60 minutes the first time)
"""

import os
import pickle
import warnings

import numpy as np
import pandas as pd
from statsbombpy import sb

from step1_build_minutes import POSITION_GROUPS, match_end_minute, minutes_from_lineups
from step2_metrics import LABELS, count_events

warnings.filterwarnings("ignore")

LEAGUES = {"Premier League": 2, "La Liga": 11, "Serie A": 12, "Ligue 1": 7}
SEASON_ID = 27  # 2015/16
CHECKPOINT = "data/season_checkpoint.pkl"
OUTPUT = "data/season_2015_16.csv"

# Columns count_events() expects. A single match may not contain every event type,
# so add any that are missing as empty columns.
NEEDED = ["pass_type", "pass_outcome", "pass_end_location", "pass_shot_assist", "pass_goal_assist",
          "shot_type", "shot_statsbomb_xg", "shot_key_pass_id", "carry_end_location", "dribble_outcome",
          "duel_type", "duel_outcome", "interception_outcome", "ball_recovery_recovery_failure", "location"]


def load_checkpoint():
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "rb") as f:
            return pickle.load(f)
    return {"done": set(), "spells": [], "counts": []}


def save_checkpoint(state):
    with open(CHECKPOINT, "wb") as f:
        pickle.dump(state, f)


def main():
    os.makedirs("data", exist_ok=True)
    state = load_checkpoint()

    for league, comp_id in LEAGUES.items():
        matches = sb.matches(competition_id=comp_id, season_id=SEASON_ID)
        todo = [m for m in matches["match_id"] if m not in state["done"]]
        print(f"{league}: {len(matches)} matches ({len(todo)} still to download)")

        for i, match_id in enumerate(todo, start=1):
            events = sb.events(match_id=match_id)
            for col in NEEDED:
                if col not in events.columns:
                    events[col] = np.nan
            lineups = sb.lineups(match_id=match_id)

            spells = minutes_from_lineups(lineups, match_id, match_end_minute(events))
            for s in spells:
                s["league"] = league
            state["spells"] += spells
            state["counts"].append(count_events(events))
            state["done"].add(match_id)

            if i % 50 == 0 or i == len(todo):
                save_checkpoint(state)
            print(f"  {i}/{len(todo)}", end="\r")
        print()

    # ---- Season totals per player ----
    spells = pd.DataFrame(state["spells"])
    spells["position_group"] = spells["position"].map(POSITION_GROUPS)

    group_minutes = (spells.groupby(["player_id", "position_group"])["minutes"].sum()
                     .reset_index().sort_values("minutes", ascending=False))
    primary = group_minutes.drop_duplicates("player_id").set_index("player_id")["position_group"]

    # A player can change club mid-season: report the club where he played most minutes
    team_minutes = (spells.groupby(["player_id", "team", "league"])["minutes"].sum()
                    .reset_index().sort_values("minutes", ascending=False)
                    .drop_duplicates("player_id").set_index("player_id"))

    players = (spells.groupby("player_id")
               .agg(player_name=("player_name", "first"), matches=("match_id", "nunique"),
                    minutes=("minutes", "sum")).reset_index())
    players["team"] = players["player_id"].map(team_minutes["team"])
    players["league"] = players["player_id"].map(team_minutes["league"])
    players["primary_group"] = players["player_id"].map(primary)
    players["minutes"] = players["minutes"].round(0).astype(int)

    counts = pd.concat(state["counts"]).groupby(level=0).sum()
    df = players.merge(counts, left_on="player_id", right_index=True, how="left").fillna(0)

    df["pass_completion"] = 100 * df["passes_completed"] / df["passes_attempted"].replace(0, np.nan)
    for col in [c for c in LABELS if c != "pass_completion"]:
        df[col] = df[col] / df["minutes"] * 90

    df = df.drop(columns=["passes_attempted"]).round(3)
    df.to_csv(OUTPUT, index=False)
    print(f"Saved {len(df)} players to {OUTPUT}")
    print(df.groupby("league")["player_id"].count())


if __name__ == "__main__":
    main()
