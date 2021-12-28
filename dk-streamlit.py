import streamlit as st
import pandas as pd
import numpy as np
from draft_kings import Client
from draft_kings.data import Sport
from draft_kings import Sport, Client
from collections import defaultdict
from pprint import pprint
import pulp

st.title('DK Lineup Optimizer')

# constants
SALARY_MAX = 50000
salary_min = 0
MAX_PLAYERS = 9

# get contest data from API
contests = Client().contests(sport=Sport.NFL)
contest_ids = [(n.name, n.contest_id, n.draft_group_id) for n in contests.contests]

# input box for available contests
contest_selected = st.selectbox(
    label="Contests",
    options=contest_ids
)

# contest_selected = st.multiselect(
#     label="Contests:", 
#     options=contest_ids,
#     default=contest_ids[0]
# )

try:
    # print out the selection
    st.write('You selected:', contest_selected[0])
except:
    raise IndexError("Pick only 1 contest from the list")


# get the draft group ID from the input selection
draft_group_id = contest_selected[2]

players_details = Client().available_players(draft_group_id=draft_group_id).players

# create dictionary of players
rows_list = []
for p in players_details:
    p_data = {
        "player_id": p.player_id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "position": p.position_details.name,
        "fppg": round(p.points_per_game, 1),
        "opp_rank": p.team_series_details.opposition_rank,
        "salary": int(round(p.draft_details.salary, 0))
    }

    rows_list.append(p_data)

df = pd.DataFrame(rows_list)
df = df[df["salary"] >= salary_min]
df = df.reset_index(drop=True)
player_exclusion_options = df["first_name"] + "_" + df["last_name"]

# print out available players
st.header('Draft list:')
st.dataframe(data=df.drop(columns="player_id"), width=800, height=None)

players_expanded = df["position"] + "_" + df["first_name"] + "_" + df["last_name"] + "_" + df["player_id"].astype(str) + " (" + df["salary"].astype(int).astype(str) + ")"
df['players_expanded'] = players_expanded

# create exclusions list
exclusions = st.multiselect(
    label="Exclusions (injured players are not automatically excluded):", 
    options=players_expanded
)

names = [p.split("_") for p in exclusions]
names_tuple = [(x[1], x[2]) for x in names]

first_names = [e[0] for e in names_tuple]
last_names = [e[1] for e in names_tuple]

st.write('You excluded:', exclusions)

# update the dataframe
df_updated = df[~(df.last_name.isin(last_names)) & ~df.first_name.isin(first_names)]

#st.header('Updated draft list:')
#st.dataframe(data=df_updated.drop(columns="player_id"), width=None, height=None)

# optimize the lineup
@st.cache
def lineup_optimizer(df_updated):
    
    # update the player list and other data
    players = df_updated["position"] + "_" + df_updated["first_name"] + "_" + df_updated["last_name"] + "_" + df_updated["player_id"].astype(str) + " (" + df_updated["salary"].astype(int).astype(str) + ")"
    df_updated['players_expanded'] = players
    positions = df_updated["position"]
    ppg = df_updated["fppg"]
    salary = df_updated["salary"]
    total_players = len(players)

    solver = pulp.getSolver('COIN_CMD')
    prob = pulp.LpProblem("dk", pulp.LpMaximize)
    # binary variable for selecting each player
    player_vars = [pulp.LpVariable(p, cat="Binary") for p in players]
    # add salary constraint
    prob += pulp.lpSum(player_vars * salary) <= SALARY_MAX
    # add total players constraint
    prob += pulp.lpSum(player_vars) == MAX_PLAYERS
    # binary series for each position type
    wrs = pd.Series([1 if p in "WR" else 0 for p in positions])
    rbs = pd.Series([1 if p in "RB" else 0 for p in positions])
    qbs = pd.Series([1 if p in "QB" else 0 for p in positions])
    te = pd.Series([1 if p in "TE" else 0 for p in positions])
    dst = pd.Series([1 if p in "DST" else 0 for p in positions])
    # add 1 QB constraint
    prob += pulp.lpSum(player_vars * qbs) == 1
    # add 1 DST constraint
    prob += pulp.lpSum(player_vars * dst) == 1
    # add at least 2 RB constraint
    prob += pulp.lpSum(player_vars * rbs) >= 2
    # add at least 3 WR constraint
    prob += pulp.lpSum(player_vars * wrs) >= 3
    # add at least 1 TE constraint
    prob += pulp.lpSum(player_vars * te) >= 1
    # total team average points
    prob += pulp.lpSum(player_vars * ppg)
    prob.solve()
    # # optimization selections
    selected = [str(p) for p in player_vars if p.value() == 1]
    return selected

selected = lineup_optimizer(df_updated)
print(selected)

# # print out available players
st.header('Optimal lineup (FPPG):')
#st.write(selected)

selected_ids = [int(p.split("_")[3]) for p in selected]

selected_df = df[df["player_id"].isin(selected_ids)]
st.dataframe(data=selected_df.drop(columns=["player_id", "players_expanded"]))

# confirm that salary is under the cap
st.write('Lineup total salary:', sum(selected_df.salary))