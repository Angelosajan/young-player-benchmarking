"""
Young Player Benchmarking - Euro 2024 & Copa America 2024 (StatsBomb open data)
Pick an under-21 player and see how their per-90 output compares with every player
in the same position group at the two tournaments, plus a short development summary.
Run locally:  streamlit run app.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from step2_metrics import LABELS, LOWER_IS_BETTER, MIN_MINUTES, TEMPLATES

SMALL_SAMPLE = 360          # under 4 full matches: flag results as provisional
STRENGTH, DEVELOP = 70, 35  # percentile cut-offs used in the summary

st.set_page_config(page_title="Young Player Benchmarking", layout="wide")


@st.cache_data
def load():
    df = pd.read_csv("data/player_metrics.csv")
    df["age"] = df["age"].astype("Int64")
    return df


def radar(values, labels, compare=None, compare_name=None, name=None):
    """Percentile radar (0-100). Optional second player overlaid for comparison."""
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]
    fig, ax = plt.subplots(figsize=(5.5, 5.5), subplot_kw={"polar": True})

    def draw(vals, colour, label):
        vals = list(vals) + [vals[0]]
        ax.plot(angles, vals, color=colour, linewidth=2, label=label)
        ax.fill(angles, vals, color=colour, alpha=0.2)

    draw(values, "#132257", name)
    if compare is not None:
        draw(compare, "#C0392B", compare_name)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.12), fontsize=8, frameon=False)

    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75])
    ax.set_yticklabels(["25", "50", "75"], fontsize=7, color="grey")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=8)
    ax.spines["polar"].set_visible(False)
    fig.tight_layout()
    return fig


def ordinal(n):
    n = int(n)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def summary(row, metrics):
    """Plain-language strengths and development areas from the percentiles."""
    pcts = {LABELS[m]: row[f"{m}_pct"] for m in metrics}
    strengths = sorted([k for k, v in pcts.items() if v >= STRENGTH], key=lambda k: -pcts[k])
    develop = sorted([k for k, v in pcts.items() if v <= DEVELOP], key=lambda k: pcts[k])

    lines = []
    if strengths:
        lines.append("**Strengths relative to positional peers:** " +
                     ", ".join(f"{k} ({ordinal(pcts[k])} pct)" for k in strengths) + ".")
    else:
        lines.append("**Strengths:** no metric in the top 30% of positional peers at these tournaments.")
    if develop:
        lines.append("**Possible development areas:** " +
                     ", ".join(f"{k} ({ordinal(pcts[k])} pct)" for k in develop) + ".")
    else:
        lines.append("**Development areas:** no metric in the bottom 35% of positional peers.")
    lines.append("Use these as prompts for video review and conversation with coaches, "
                 "not as conclusions: tournament samples are small and role-dependent.")
    return lines


df = load()
u21 = df[df["is_u21"]].sort_values("minutes", ascending=False)

st.title("Young Player Benchmarking")
st.caption("Euro 2024 & Copa América 2024 · StatsBomb open data · "
           f"U21 outfield players with {MIN_MINUTES}+ minutes, benchmarked against all ages in their position group")

tab_player, tab_overview, tab_method = st.tabs(["Player profile", "U21 overview", "Method & limitations"])

# ---------------- Player profile ----------------
with tab_player:
    left, right = st.columns([1, 2])
    with left:
        groups = ["All positions"] + list(TEMPLATES)
        group = st.selectbox("Position group", groups)
        pool = u21 if group == "All positions" else u21[u21["primary_group"] == group]
        player_name = st.selectbox("U21 player", pool["player_name"] + " (" + pool["team"] + ")")
        row = pool[(pool["player_name"] + " (" + pool["team"] + ")") == player_name].iloc[0]

        peers = df[df["primary_group"] == row["primary_group"]]
        others = peers[peers["player_id"] != row["player_id"]].sort_values("player_name")
        compare_name = st.selectbox("Compare with (optional, same position group)",
                                    ["None"] + list(others["player_name"] + " (" + others["team"] + ")"))

    metrics = TEMPLATES[row["primary_group"]]
    compare_row = None
    if compare_name != "None":
        compare_row = others[(others["player_name"] + " (" + others["team"] + ")") == compare_name].iloc[0]

    with right:
        st.subheader(f"{row['player_name']} · {row['team']}")
        st.caption(f"Position group: {row['primary_group']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Age (1 Jul 2024)", int(row["age"]))
        c2.metric("Minutes", int(row["minutes"]))
        c3.metric("Matches", int(row["matches"]))
        if row["minutes"] < SMALL_SAMPLE:
            st.warning(f"Small sample: {int(row['minutes'])} minutes. Treat these numbers as provisional.")

    col_radar, col_table = st.columns([1, 1])
    with col_radar:
        fig = radar([row[f"{m}_pct"] for m in metrics], [LABELS[m] for m in metrics],
                    compare=None if compare_row is None else [compare_row[f"{m}_pct"] for m in metrics],
                    compare_name=None if compare_row is None else compare_row["player_name"],
                    name=row["player_name"])
        st.pyplot(fig)
        st.caption(f"Percentile vs {int(row['group_size'])} {row['primary_group'].lower()} players (all ages). "
                   "50 = typical for the position.")
    with col_table:
        table = pd.DataFrame({
            "Metric": [LABELS[m] + (" (lower is better)" if m in LOWER_IS_BETTER else "") for m in metrics],
            "Per 90": [row[m] for m in metrics],
            "Position median": [peers[m].median() for m in metrics],
            "Percentile": [int(row[f"{m}_pct"]) for m in metrics],
        })
        table.loc[table["Metric"].str.startswith("Pass completion"), "Metric"] = "Pass completion % (not per 90)"
        st.dataframe(table, hide_index=True, width="stretch",
                     column_config={"Per 90": st.column_config.NumberColumn(format="%.2f"),
                                    "Position median": st.column_config.NumberColumn(format="%.2f"),
                                    "Percentile": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                                                  format="%d")})
        st.markdown("#### Development summary")
        for line in summary(row, metrics):
            st.markdown(line)

# ---------------- Overview ----------------
with tab_overview:
    st.markdown("All U21 outfield players with enough minutes. Click a column header to sort.")
    overview = u21[["player_name", "team", "age", "primary_group", "minutes",
                    "progressive_carries", "progressive_passes", "key_passes", "np_xg", "tackles_interceptions"]]
    st.dataframe(overview.rename(columns={"player_name": "Player", "team": "Team", "age": "Age",
                                          "primary_group": "Position group", "minutes": "Minutes",
                                          **{k: LABELS[k] + " /90" for k in LABELS}}),
                 hide_index=True, width="stretch")
    counts = u21["primary_group"].value_counts()
    st.caption("U21 players by position group: " + ", ".join(f"{g} {n}" for g, n in counts.items()) +
               ". Young players are concentrated in attacking roles at senior tournaments.")

# ---------------- Method ----------------
with tab_method:
    st.markdown(f"""
**Data.** StatsBomb open event data for UEFA Euro 2024 (51 matches) and Copa América 2024 (32 matches).
Birth dates from the tournaments' published squad lists, linked to StatsBomb player IDs.

**Who is included.** Outfield players with at least {MIN_MINUTES} minutes. U21 = aged 21 or under on 1 July 2024.
Each player is assigned the position group where they played most minutes.

**Metrics.** Per-90 rates from event data. *Progressive* passes/carries move the ball at least 30 units closer
to goal within a team's own half, 15 when crossing halfway and 10 in the opposition half. Set pieces and
penalty shoot-outs are excluded. xG and xA use StatsBomb's xG model; penalties are excluded.

**Percentiles.** Ranked against all players (any age) in the same position group.

**Limitations.**
- Tournament samples are small (3–7 matches); a player's numbers can swing with one game.
- Output depends on team style and role, not only individual ability.
- Position groups follow StatsBomb's formation tags and may differ from how a coach sees a player.
- Event data does not capture off-ball movement or physical output (tracking/GPS data would).
""")
