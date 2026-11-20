"""
Step 1 - Download StatsBomb open data and build a player-minutes table.
Tournaments: UEFA Euro 2024 and Copa America 2024 (both free in StatsBomb open data).
Outputs (in data/):
  events.pkl          every event from every match (used in step 2)
  player_minutes.csv  one row per player: team, primary position group, matches, minutes
"""
import os
import warnings
import pandas as pd
from statsbombpy import sb

warnings.filterwarnings("ignore")  # statsbombpy warns that we're not using paid credentials

COMPETITIONS = [
    {"name": "Euro 2024", "competition_id": 55, "season_id": 282},
    {"name": "Copa America 2024", "competition_id": 223, "season_id": 282},
]
DATA_DIR = "data"

# Map StatsBomb's detailed positions to 6 broad groups.
# Players are only benchmarked against others in the same group.
POSITION_GROUPS = {
    "Goalkeeper": "Goalkeeper",
    "Center Back": "Centre-back", "Left Center Back": "Centre-back", "Right Center Back": "Centre-back",
    "Left Back": "Full-back", "Right Back": "Full-back",
    "Left Wing Back": "Full-back", "Right Wing Back": "Full-back",
    "Defensive Midfield": "Central midfield", "Center Defensive Midfield": "Central midfield",
    "Left Defensive Midfield": "Central midfield", "Right Defensive Midfield": "Central midfield",
    "Center Midfield": "Central midfield", "Left Center Midfield": "Central midfield",
    "Right Center Midfield": "Central midfield",
    "Center Attacking Midfield": "Attacking mid / winger", "Left Attacking Midfield": "Attacking mid / winger",
    "Right Attacking Midfield": "Attacking mid / winger", "Left Midfield": "Attacking mid / winger",
    "Right Midfield": "Attacking mid / winger", "Left Wing": "Attacking mid / winger",
    "Right Wing": "Attacking mid / winger",
    "Center Forward": "Striker", "Left Center Forward": "Striker", "Right Center Forward": "Striker",
    "Secondary Striker": "Striker",
}


def clock_to_minutes(clock):
    """Convert a StatsBomb 'MM:SS' match clock to minutes as a float."""
    mins, secs = clock.split(":")
    return int(mins) + int(secs) / 60


def match_end_minute(events):
    """Last moment of open play (excludes penalty shoot-outs, which are period 5)."""
    play = events[events["period"] <= 4]
    return (play["minute"] + play["second"] / 60).max()


def minutes_from_lineups(lineups, match_id, end_minute):
    """One row per player per position spell in this match."""
    rows = []
    for team, squad in lineups.items():
        for _, player in squad.iterrows():
            # Many players have no nickname (NaN). NaN counts as "true" in Python,
            # so check explicitly - otherwise the name is blank and the player is lost.
            nickname = player["player_nickname"]
            display_name = nickname if pd.notna(nickname) else player["player_name"]
            for spell in player["positions"]:
                start = clock_to_minutes(spell["from"])
                end = clock_to_minutes(spell["to"]) if spell["to"] else end_minute
                rows.append({
                    "match_id": match_id,
                    "player_id": player["player_id"],
                    "player_name": display_name,
                    "full_name": player["player_name"],
                    "team": team,
                    "position": spell["position"],
                    "minutes": max(end - start, 0),
                })
    return rows


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    all_events, spells = [], []

    for comp in COMPETITIONS:
        matches = sb.matches(competition_id=comp["competition_id"], season_id=comp["season_id"])
        print(f"{comp['name']}: {len(matches)} matches")
        for i, match_id in enumerate(matches["match_id"], start=1):
            events = sb.events(match_id=match_id)
            events["competition"] = comp["name"]
            lineups = sb.lineups(match_id=match_id)
            spells += minutes_from_lineups(lineups, match_id, match_end_minute(events))
            all_events.append(events)
            print(f"  {i}/{len(matches)} downloaded", end="\r")
        print()

    events = pd.concat(all_events, ignore_index=True)
    events.to_pickle(os.path.join(DATA_DIR, "events.pkl"))

    spells = pd.DataFrame(spells)
    spells["position_group"] = spells["position"].map(POSITION_GROUPS)

    # Primary position group = the group where the player spent most minutes
    group_minutes = (spells.groupby(["player_id", "position_group"])["minutes"].sum()
                     .reset_index().sort_values("minutes", ascending=False))
    primary = group_minutes.drop_duplicates("player_id").set_index("player_id")["position_group"]

    players = (spells.groupby(["player_id", "player_name", "full_name", "team"])
               .agg(matches=("match_id", "nunique"), minutes=("minutes", "sum"))
               .reset_index())
    players["primary_group"] = players["player_id"].map(primary)
    players["minutes"] = players["minutes"].round(0).astype(int)
    players = players.sort_values("minutes", ascending=False)

    players.to_csv(os.path.join(DATA_DIR, "player_minutes.csv"), index=False)
    print(f"Saved {len(players)} players and {len(events):,} events to {DATA_DIR}/")


if __name__ == "__main__":
    main()
