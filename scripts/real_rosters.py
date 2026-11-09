"""
Rate real MLB player-seasons on our 1-100 skill scale and build team rosters.

Spike for docs/brainstorming/skill_mapping_from_stats.md. Reads the Lahman
database (the pylahman package ships it as parquet files) and, for a list of
real team-seasons, prints each roster with our 17 skills.

How a skill is rated
--------------------
1. Each skill has a stat (or a blend of stats) from the real line, e.g. power
   is ISO, accuracy is unintentional walks + HBP per batter faced (inverted).
2. The stat is shrunk toward the league mean by sample size, so a 30 PA
   season can't rank first or last.
3. It becomes a z-score against that league-season's regulars (same year,
   same league, and same position for defense). That makes it era-relative:
   leading the 1968 AL in power rates like leading the 2001 AL.
4. 70% that season, 30% his three-season window around it (y-1..y+1).
5. The z-score's percentile is looked up in our own generated 26-man rosters
   for the same skill and position, so a 90th-percentile real hitter gets
   the skill a 90th-percentile generated hitter has. Imports then sit on the
   same scale and grade curves as every other player.

Skills Lahman can't see (clutch, and pitchers' durability) get the generated
median for that position plus a little seeded noise.

Usage (the "stats" extra brings pandas, pyarrow and the Lahman data):
    uv run --extra stats python -m scripts.real_rosters
        [--teams 1961:NYA,2001:SEA,1986:NYN] [--json OUT.json]
        [--workload modern|era] [--data DIR]
    uv run --extra stats python -m scripts.real_rosters --export-season 2025

    uv run --extra stats python -m scripts.real_rosters --export-players

--export-season writes the data file a real-season league starts from
(src/league/real_seasons/data/YEAR.json). --export-players writes every
player-season with 100+ PA or 30+ IP (data/players.tsv.gz), the pool custom
teams pick from.

--data is a folder of Lahman parquet files (Batting, Pitching, Fielding,
People, Appearances, Teams). It defaults to the copy inside the pylahman
package; pass it only to use a newer or different copy.
"""

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.api.grade_curves import overall_to_grade
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.team.team_factory import TeamFactory

SKILL_ORDER = [
    "contact",
    "power",
    "eye",
    "speed",
    "base_running",
    "bunting",
    "durability",
    "clutch",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "strikes",
    "ground_balls",
    "stamina",
    "recovery",
]
HIT_SKILLS = ["contact", "power", "eye", "speed", "base_running", "bunting"]
PITCH_SKILLS = ["accuracy", "strikes", "ground_balls", "stamina", "recovery"]
FIELD_POS = ["c", "1b", "2b", "ss", "3b", "lf", "cf", "rf"]
INFIELD = ("1b", "2b", "ss", "3b")
OUTFIELD = ("lf", "cf", "rf")

MIN_PA = 100  # a hitter's season counts from 100 plate appearances
MIN_IPOUTS = 90  # a pitcher's from 30 innings
ROSTER_HITTERS = 13  # a generated 26-man roster's split
ROSTER_PITCHERS = 13
SEASON_WEIGHT = 0.7
# "modern": stamina and recovery against 2015-2025 pitchers (workloads keep
# their era), "era": against his own season like every other skill.
WORKLOAD = "modern"
MODERN_YEARS = (2015, 2025)  # rest goes to the 3-season window


# ---------------------------------------------------------------- reference


def reference_pools(n_teams: int, seed: int = 7) -> dict:
    """Skill values of generated 26-man roster players, by affinity position.

    The same population scripts/calibrate_overall_grades.py curves grades on.
    Returns {position: {skill: sorted list}} plus "hitter" (all position
    players) and "pitcher" (sp + rp).
    """
    factory = TeamFactory(rng=random.Random(seed))
    pools: dict = defaultdict(lambda: defaultdict(list))
    for i in range(n_teams):
        team = factory.generate_team(city=f"Ref{i}", mascot="Sims", size=26)
        for p in team.players:
            group = "pitcher" if p.position in ("sp", "rp") else "hitter"
            for skill, value in p.skills.as_dict().items():
                pools[p.position][skill].append(value)
                pools[group][skill].append(value)
    return {
        pos: {s: sorted(v) for s, v in skills.items()} for pos, skills in pools.items()
    }


def quantile(values: list[int], pct: float) -> float:
    """Linear-interpolated quantile of a sorted list."""
    pct = min(max(pct, 0.0), 1.0)
    idx = pct * (len(values) - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (idx - lo)


def median(values: list[int]) -> float:
    return quantile(values, 0.5)


def phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def to_skill(z: float | None, pool: list[int]) -> float:
    """z-score among real regulars -> our skill at the same percentile."""
    if z is None or pd.isna(z):
        return median(pool)
    pct = min(max(phi(z), 0.001), 0.999)
    return quantile(pool, pct)


# ---------------------------------------------------------------- data


def load(data_dir: Path) -> dict[str, pd.DataFrame]:
    names = ["Batting", "Pitching", "Fielding", "People", "Appearances", "Teams"]
    d = {n: pd.read_parquet(data_dir / f"{n}.parquet") for n in names}
    d["Pitching"] = d["Pitching"].rename(columns={"IPOuts": "IPouts"})
    for n, df in d.items():
        for c in df.columns:
            if str(df[c].dtype) in ("string", "str"):
                df[c] = df[c].astype(object).where(df[c].notna(), None)
    return d


def num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df


def team_games(teams: pd.DataFrame) -> pd.DataFrame:
    """Games per team-season and the league's typical team schedule."""
    t = teams[["yearID", "lgID", "teamID", "G"]].copy()
    t["lgG"] = t.groupby(["yearID", "lgID"])["G"].transform("max")
    return t


def primary_league(rows: pd.DataFrame, weight: str) -> pd.Series:
    """The league a player-year spent most of his time in."""
    idx = rows.groupby(["playerID", "yearID"])[weight].idxmax()
    return rows.loc[idx].set_index(["playerID", "yearID"])["lgID"]


def shrink(x: pd.Series, n: pd.Series, mu: pd.Series, k: float) -> pd.Series:
    return (x * n + mu * k) / (n + k)


def zscore(
    df: pd.DataFrame, col: str, regular: pd.Series, group: list[str]
) -> pd.Series:
    """z of df[col] against regulars in the same group (NaN-safe)."""
    reg = df[regular & df[col].notna()]
    stats = (
        reg.groupby(group)[col]
        .agg(["mean", "std"])
        .rename(columns={"mean": "_m", "std": "_s"})
    )
    merged = df[group].join(stats, on=group)
    return (df[col] - merged["_m"]) / merged["_s"]


def group_mean(
    df: pd.DataFrame, col: str, regular: pd.Series, group: list[str]
) -> pd.Series:
    reg = df[regular & df[col].notna()]
    m = reg.groupby(group)[col].mean().rename("_m")
    return df[group].join(m, on=group)["_m"]


def blend_window(df: pd.DataFrame, zcol: str, wcol: str) -> pd.Series:
    """0.7 x this season + 0.3 x his weight-averaged y-1..y+1 seasons."""
    d = df[["playerID", "yearID", zcol, wcol]].dropna(subset=[zcol])
    by_player = defaultdict(dict)
    for pid, yr, z, w in d.itertuples(index=False):
        by_player[pid][yr] = (z, w)
    out = []
    for pid, yr, z in df[["playerID", "yearID", zcol]].itertuples(index=False):
        if z is None or pd.isna(z):
            out.append(float("nan"))
            continue
        seasons = by_player[pid]
        tot = wsum = 0.0
        for y in (yr - 1, yr, yr + 1):
            if y in seasons:
                zz, w = seasons[y]
                tot += zz * w
                wsum += w
        window = tot / wsum if wsum else z
        out.append(SEASON_WEIGHT * z + (1 - SEASON_WEIGHT) * window)
    return pd.Series(out, index=df.index)


# ---------------------------------------------------------------- hitting


def hitting_table(d: dict, tg: pd.DataFrame) -> pd.DataFrame:
    b = num(
        d["Batting"].copy(),
        [
            "G",
            "AB",
            "R",
            "H",
            "2B",
            "3B",
            "HR",
            "SB",
            "CS",
            "BB",
            "SO",
            "IBB",
            "HBP",
            "SH",
            "SF",
            "GIDP",
        ],
    )
    for c in ["IBB", "HBP", "SH", "SF"]:
        b[c] = b[c].fillna(0)
    b["PA"] = b["AB"] + b["BB"] + b["HBP"] + b["SH"] + b["SF"]
    lg = primary_league(b, "PA")
    sums = [
        "G",
        "AB",
        "R",
        "H",
        "2B",
        "3B",
        "HR",
        "SB",
        "CS",
        "BB",
        "SO",
        "IBB",
        "HBP",
        "SH",
        "SF",
        "PA",
    ]
    h = b.groupby(["playerID", "yearID"])[sums].sum(min_count=1).reset_index()
    h["lgID"] = lg.reindex(pd.MultiIndex.from_frame(h[["playerID", "yearID"]])).values
    lgG = tg.groupby(["yearID", "lgID"])["lgG"].max()
    h = h.join(lgG, on=["yearID", "lgID"])

    # Pitchers hit in their own pool.
    a = num(d["Appearances"].copy(), ["G_p", "G_batting", "G_defense", "G_all"])
    ap = a.groupby(["playerID", "yearID"])[["G_p", "G_all"]].sum()
    h = h.join(ap, on=["playerID", "yearID"])
    h["is_pitcher"] = (h["G_p"].fillna(0) >= 0.5 * h["G_all"].fillna(1)) & (
        h["G_p"].fillna(0) > 0
    )

    h["pool"] = h["is_pitcher"].map({True: "p", False: "h"})
    # Compare against what our generated 26-man rosters hold: each team's
    # 13 position players with the most playing time, bench included.
    b = b.join(
        h.set_index(["playerID", "yearID"])["is_pitcher"], on=["playerID", "yearID"]
    )
    hb = b[~b["is_pitcher"].fillna(False).astype(bool)].copy()
    hb["rank"] = hb.groupby(["yearID", "teamID"])["PA"].rank(
        ascending=False, method="first"
    )
    top = (
        hb[hb["rank"] <= ROSTER_HITTERS]
        .set_index(["playerID", "yearID"])
        .index.unique()
    )
    h["regular"] = (
        ~h["is_pitcher"] & pd.MultiIndex.from_frame(h[["playerID", "yearID"]]).isin(top)
    ) | (h["is_pitcher"] & (h["PA"] >= 0.15 * h["lgG"]))
    h["everyday"] = ~h["is_pitcher"] & (h["PA"] >= 1.25 * h["lgG"])
    grp = ["yearID", "lgID", "pool"]

    def rate(name: str, x: pd.Series, n: pd.Series, k: float, sign: float = 1.0):
        h[f"_raw_{name}"] = x / n.where(n > 0)
        mu = group_mean(h, f"_raw_{name}", h["regular"], grp)
        h[f"_{name}"] = sign * shrink(h[f"_raw_{name}"], n, mu, k)

    so_known = h["SO"].notna()
    rate("k", h["SO"], h["PA"], 60, -1)
    rate(
        "babip", h["H"] - h["HR"], h["AB"] - h["SO"].fillna(0) - h["HR"] + h["SF"], 400
    )
    rate("iso", h["2B"] + 2 * h["3B"] + 3 * h["HR"], h["AB"], 160)
    rate("bb", h["BB"] - h["IBB"], h["PA"], 120)
    on_first = h["H"] - h["2B"] - h["3B"] - h["HR"] + h["BB"] + h["HBP"]
    rate("sba", h["SB"] + h["CS"].fillna(0), on_first, 40)
    rate("trip", h["3B"], h["2B"] + h["3B"], 25)
    rate("sbpct", h["SB"], h["SB"] + h["CS"], 15)
    h.loc[h["CS"].isna(), "_sbpct"] = float("nan")
    rate("run", h["R"] - h["HR"], h["H"] + h["BB"] + h["HBP"] - h["HR"], 80)
    rate("sh", h["SH"], h["PA"], 60)
    h["_gshare"] = h["G"] / h["lgG"]
    h.loc[~so_known, "_k"] = float("nan")

    for col in [
        "_k",
        "_babip",
        "_iso",
        "_bb",
        "_sba",
        "_trip",
        "_sbpct",
        "_run",
        "_sh",
        "_gshare",
    ]:
        h["z" + col] = zscore(h, col, h["regular"], grp)

    def combo(parts: list[tuple[str, float]]) -> pd.Series:
        tot = pd.Series(0.0, index=h.index)
        wsum = pd.Series(0.0, index=h.index)
        for col, w in parts:
            z = h["z" + col]
            tot += z.fillna(0) * w
            wsum += z.notna() * w
        return tot / wsum.where(wsum > 0)

    raw = {
        "contact": combo([("_k", 0.5), ("_babip", 0.5)]),
        "power": h["z_iso"],
        "eye": h["z_bb"],
        "speed": combo([("_sba", 0.6), ("_trip", 0.4)]),
        "base_running": combo([("_sbpct", 0.5), ("_run", 0.5)]),
        "bunting": h["z_sh"],
        "durability": h["z_gshare"],
    }
    for skill, s in raw.items():
        # Composite z's spread less than 1: put them back on the regulars' scale.
        h["c_" + skill] = s
        h["c_" + skill] = zscore(h, "c_" + skill, h["regular"], grp)
        h["z_" + skill] = blend_window(h, "c_" + skill, "PA")
    # A bench player's few games say nothing about how often he gets hurt.
    h.loc[~h["everyday"], "z_durability"] = float("nan")
    return h.set_index(["playerID", "yearID"])


# ---------------------------------------------------------------- pitching


def pitching_table(d: dict, tg: pd.DataFrame) -> pd.DataFrame:
    p = num(
        d["Pitching"].copy(),
        ["G", "GS", "IPouts", "H", "HR", "BB", "SO", "IBB", "HBP", "BFP", "WP", "GIDP"],
    )
    for c in ["IBB", "HBP", "WP"]:
        p[c] = p[c].fillna(0)
    p["BFP"] = p["BFP"].fillna(p["IPouts"] + p["H"] + p["BB"] + p["HBP"])
    lg = primary_league(p, "BFP")
    sums = ["G", "GS", "IPouts", "H", "HR", "BB", "SO", "IBB", "HBP", "BFP", "WP"]
    q = p.groupby(["playerID", "yearID"])[sums].sum(min_count=1).reset_index()
    q["lgID"] = lg.reindex(pd.MultiIndex.from_frame(q[["playerID", "yearID"]])).values
    q = q.join(tg.groupby(["yearID", "lgID"])["lgG"].max(), on=["yearID", "lgID"])
    q["role"] = (q["GS"] >= 0.5 * q["G"]).map({True: "sp", False: "rp"})
    p["rank"] = p.groupby(["yearID", "teamID"])["BFP"].rank(
        ascending=False, method="first"
    )
    top = (
        p[p["rank"] <= ROSTER_PITCHERS].set_index(["playerID", "yearID"]).index.unique()
    )
    q["regular"] = pd.MultiIndex.from_frame(q[["playerID", "yearID"]]).isin(top)
    q["everyday"] = ((q["role"] == "sp") & (q["GS"] >= 0.06 * q["lgG"])) | (
        (q["role"] == "rp") & (q["G"] >= 0.15 * q["lgG"])
    )
    grp = ["yearID", "lgID"]
    rgrp = ["yearID", "lgID", "role"]

    def rate(name, x, n, k, sign=1.0, group=grp):
        q[f"_raw_{name}"] = x / n.where(n > 0)
        mu = group_mean(q, f"_raw_{name}", q["regular"], group)
        q[f"_{name}"] = sign * shrink(q[f"_raw_{name}"], n, mu, k)

    rate("kk", q["SO"], q["BFP"], 70)
    rate("bb", q["BB"] - q["IBB"] + q["HBP"] + 0.5 * q["WP"], q["BFP"], 170, -1)
    rate("hr", q["HR"], q["BFP"] - q["SO"] - q["BB"] - q["HBP"], 500, -1)
    q["_stam"] = q["IPouts"] / q["G"]
    q["_rec"] = q["GS"].where(q["role"] == "sp", q["G"]) / q["lgG"]
    for col in ["_kk", "_bb", "_hr"]:
        q["z" + col] = zscore(q, col, q["regular"], grp)
    for col in ["_stam", "_rec"]:
        if WORKLOAD == "era":
            q["z" + col] = zscore(q, col, q["regular"], rgrp)
        else:
            # Workload is measured against today's pitchers, not his own
            # season's: a 1961 ace who threw 7+ innings every fourth day
            # really could carry more than a 2024 one.
            ref = q[q["regular"] & q["yearID"].between(*MODERN_YEARS)]
            st = ref.groupby("role")[col].agg(["mean", "std"])
            m = q["role"].map(st["mean"])
            sd = q["role"].map(st["std"])
            q["z" + col] = (q[col] - m) / sd
    names = {
        "strikes": "_kk",
        "accuracy": "_bb",
        "ground_balls": "_hr",
        "stamina": "_stam",
        "recovery": "_rec",
    }
    for skill, col in names.items():
        q["z_" + skill] = blend_window(q, "z" + col, "BFP")
    # Usage-based: a mop-up arm's few outings aren't a recovery rating.
    q.loc[~q["everyday"], "z_recovery"] = float("nan")
    return q.set_index(["playerID", "yearID"])


# ---------------------------------------------------------------- fielding


def primary_positions(d: dict) -> pd.DataFrame:
    a = num(
        d["Appearances"].copy(),
        [
            "G_p",
            "G_c",
            "G_1b",
            "G_2b",
            "G_3b",
            "G_ss",
            "G_lf",
            "G_cf",
            "G_rf",
            "G_dh",
            "G_all",
        ],
    )
    cols = {
        "c": "G_c",
        "1b": "G_1b",
        "2b": "G_2b",
        "ss": "G_ss",
        "3b": "G_3b",
        "lf": "G_lf",
        "cf": "G_cf",
        "rf": "G_rf",
        "dh": "G_dh",
        "p": "G_p",
    }
    g = a.groupby(["playerID", "yearID"])[list(cols.values())].sum()
    g.columns = list(cols.keys())
    g["primary"] = g.idxmax(axis=1)
    of = g[["lf", "cf", "rf"]]
    g["of_pos"] = of.idxmax(axis=1).where(of.sum(axis=1) > 0)
    return g


def fielding_table(d: dict, tg: pd.DataFrame, prim: pd.DataFrame) -> pd.DataFrame:
    f = num(
        d["Fielding"].copy(),
        ["G", "InnOuts", "PO", "A", "E", "DP", "PB", "SB", "CS"],
    )
    f = f[f["POS"].isin(["C", "1B", "2B", "SS", "3B", "OF"])]
    lg = primary_league(f, "G")
    sums = ["G", "InnOuts", "PO", "A", "E", "DP", "PB", "SB", "CS"]
    f = f.groupby(["playerID", "yearID", "POS"])[sums].sum(min_count=1).reset_index()
    f["lgID"] = lg.reindex(pd.MultiIndex.from_frame(f[["playerID", "yearID"]])).values
    f = f.join(tg.groupby(["yearID", "lgID"])["lgG"].max(), on=["yearID", "lgID"])
    f = f.join(prim["of_pos"], on=["playerID", "yearID"])
    # Outfielders are compared to others mostly at the same OF spot.
    f["grp_pos"] = f["POS"].where(f["POS"] != "OF", "OF-" + f["of_pos"].fillna("cf"))
    f["games9"] = (f["InnOuts"] / 27).where(
        f["InnOuts"].notna() & (f["InnOuts"] > 0), f["G"]
    )
    f["regular"] = f["G"] >= 0.3 * f["lgG"]
    grp = ["yearID", "lgID", "grp_pos"]

    def rate(name, x, n, k, sign=1.0):
        f[f"_raw_{name}"] = x / n.where(n > 0)
        mu = group_mean(f, f"_raw_{name}", f["regular"], grp)
        f[f"_{name}"] = sign * shrink(f[f"_raw_{name}"], n, mu, k)

    rate("range", f["PO"] + f["A"], f["games9"], 30)
    rate("assists", f["A"], f["games9"], 40)
    rate("fpct", f["PO"] + f["A"], f["PO"] + f["A"] + f["E"], 150)
    rate("cs", f["CS"], f["SB"] + f["CS"], 40)
    rate("pb", f["PB"], f["games9"], 40, -1)
    for col in ["_range", "_assists", "_fpct", "_cs", "_pb"]:
        f["z" + col] = zscore(f, col, f["regular"], grp)

    def combo(parts):
        tot = pd.Series(0.0, index=f.index)
        wsum = pd.Series(0.0, index=f.index)
        for col, w in parts:
            z = f["z" + col]
            tot += z.fillna(0) * w
            wsum += z.notna() * w
        return tot / wsum.where(wsum > 0)

    is_1b = f["POS"] == "1B"
    f["c_glove"] = combo([("_range", 0.6), ("_fpct", 0.4)])
    f.loc[is_1b, "c_glove"] = combo([("_assists", 0.6), ("_fpct", 0.4)])[is_1b]
    is_c = f["POS"] == "C"
    f.loc[is_c, "c_glove"] = combo([("_cs", 0.5), ("_pb", 0.3), ("_fpct", 0.2)])[is_c]
    f["c_arm"] = f["z_assists"]
    f.loc[is_c, "c_arm"] = f["z_cs"][is_c]
    f.loc[is_1b, "c_arm"] = float("nan")
    for col in ["c_glove", "c_arm"]:
        f[col] = zscore(f, col, f["regular"], grp)
        f["w" + col] = blend_window(
            f.assign(playerID=f["playerID"] + "|" + f["POS"]), col, "G"
        )
    return f


# ---------------------------------------------------------------- build


def seeded_noise(key: str, sd: float) -> float:
    seed = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16)
    return random.Random(seed).gauss(0, sd)


class Rater:
    def __init__(self, data_dir: Path, ref_teams: int) -> None:
        self.d = load(data_dir)
        tg = team_games(self.d["Teams"])
        self.prim = primary_positions(self.d)
        self.hit = hitting_table(self.d, tg)
        self.pit = pitching_table(self.d, tg)
        self.fld = fielding_table(self.d, tg, self.prim)
        # Nullable ints/floats (pd.NA) break comparisons; NaN compares False.
        for name in ("hit", "pit", "fld"):
            df = getattr(self, name)
            for c in df.columns:
                if pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype.kind != "f":
                    if df[c].isna().any() or str(df[c].dtype)[0].isupper():
                        df[c] = df[c].astype("float64")
        self.fld_idx = self.fld.set_index(["playerID", "yearID", "POS"])
        self.people = self.d["People"].set_index("playerID")
        self.ref = reference_pools(ref_teams)

    def _row(self, table, pid, year):
        try:
            return table.loc[(pid, year)]
        except KeyError:
            return None

    def _field(self, pid, year, pos):
        try:
            return self.fld_idx.loc[(pid, year, pos)]
        except KeyError:
            return None

    def affinity(self, pid: str, year: int) -> str:
        pr = self._row(self.prim, pid, year)
        if pr is None:
            return "dh"
        primary = pr["primary"]
        if primary == "p":
            q = self._row(self.pit, pid, year)
            return q["role"] if q is not None else "rp"
        return primary

    def rate(self, pid: str, year: int) -> dict:
        pos = self.affinity(pid, year)
        is_p = pos in ("sp", "rp")
        ref_pos = self.ref.get(pos) or self.ref["1b" if pos == "dh" else "rp"]
        group = self.ref["pitcher" if is_p else "hitter"]
        skills: dict[str, float] = {}

        h = self._row(self.hit, pid, year)
        for s in HIT_SKILLS + ["durability"]:
            pool = ref_pos[s] if is_p else group[s]
            z = None if h is None else h["z_" + s]
            if is_p and s == "durability":
                z = None  # Lahman can't tell a durable pitcher: noise below
            if is_p and h is not None and not (h["PA"] >= 0.15 * h["lgG"]):
                # Barely batted (AL after 1972, or a reliever): he's whatever
                # a generated pitcher is.
                z = None if s != "bunting" else z
            skills[s] = to_skill(z, pool)
        # Bunting is a weak signal: halfway to the generated median.
        skills["bunting"] = 0.5 * skills["bunting"] + 0.5 * median(ref_pos["bunting"])

        q = self._row(self.pit, pid, year)
        # A two-way player (Ruth 1918, Ohtani) keeps his real pitching too.
        two_way = q is not None and q["IPouts"] >= MIN_IPOUTS
        for s in PITCH_SKILLS:
            if q is not None and (is_p or two_way):
                pool = self.ref[q["role"]][s]
                skills[s] = to_skill(q["z_" + s], pool)
            else:
                skills[s] = median(ref_pos[s])

        skills["clutch"] = median(ref_pos["clutch"]) + seeded_noise(pid + "clutch", 7)
        if is_p:
            skills["durability"] = median(ref_pos["durability"]) + seeded_noise(
                pid + "durability", 10
            )

        # Defense: his own position's glove for that skill, else the
        # generated median for his affinity position.
        glove = {"infield": None, "outfield": None, "catching": None}
        if not is_p:
            for skill, lpos in (
                ("catching", ["C"]),
                ("infield", ["SS", "2B", "3B", "1B"]),
                ("outfield", ["OF"]),
            ):
                best = None
                for lp in lpos:
                    r = self._field(pid, year, lp)
                    if r is not None and (best is None or r["G"] > best[1]["G"]):
                        best = (lp, r)
                if best is not None and best[1]["G"] >= 10:
                    lp, r = best
                    our = {
                        "C": "c",
                        "SS": "ss",
                        "2B": "2b",
                        "3B": "3b",
                        "1B": "1b",
                        "OF": self.prim.loc[(pid, year)]["of_pos"] or "cf",
                    }[lp]
                    glove[skill] = (
                        to_skill(r["wc_glove"], self.ref[our][skill]),
                        r["wc_arm"],
                        our,
                    )
        for skill in ("catching", "infield", "outfield"):
            if glove[skill] is not None:
                skills[skill] = glove[skill][0]
            else:
                skills[skill] = median(ref_pos[skill])
        prim_glove = None
        if not is_p:
            prim_glove = {
                "c": "catching",
                "1b": "infield",
                "2b": "infield",
                "ss": "infield",
                "3b": "infield",
                "lf": "outfield",
                "cf": "outfield",
                "rf": "outfield",
            }.get(pos)
        arm_z = glove[prim_glove][1] if prim_glove and glove[prim_glove] else None
        skills["arm"] = to_skill(arm_z, ref_pos["arm"])

        person = self.people.loc[pid]
        by, bm = person["birthYear"], person["birthMonth"]
        age = (
            int(year - by - (1 if (not pd.isna(bm) and bm >= 7) else 0))
            if not pd.isna(by)
            else 28
        )
        bats = {"B": "S"}.get(person["bats"], person["bats"] or "R")
        throws = person["throws"] or "R"
        ints = {s: max(1, min(100, int(round(v)))) for s, v in skills.items()}
        return {
            "id": pid,
            "name": f"{person['nameFirst']} {person['nameLast']}",
            "first": person["nameFirst"] or person["nameLast"],
            "last": person["nameLast"],
            "year": year,
            "born": None if pd.isna(by) else int(by),
            "age": age,
            "pos": pos,
            "bats": bats,
            "throws": throws if throws in ("L", "R") else "R",
            "skills": ints,
        }

    def roster(self, year: int, team: str, size: int = 40) -> list[dict]:
        a = self.d["Appearances"]
        ids = a[(a["yearID"] == year) & (a["teamID"] == team)]["playerID"].unique()
        b = self.d["Batting"]
        p = self.d["Pitching"]
        bt = (
            b[(b["yearID"] == year) & (b["teamID"] == team)]
            .groupby("playerID")[["AB", "BB"]]
            .sum()
            .sum(axis=1)
        )
        pt = (
            p[(p["yearID"] == year) & (p["teamID"] == team)]
            .groupby("playerID")["IPouts"]
            .sum()
            * 1.4
        )
        time = pd.concat([bt, pt], axis=1).fillna(0).max(axis=1)
        ids = sorted(ids, key=lambda i: -time.get(i, 0))[:size]
        out = []
        for pid in ids:
            r = self.rate(pid, year)
            r["playing_time"] = int(time.get(pid, 0))
            out.append(r)
        return out


def grades(player: dict) -> dict:
    skills = PlayerSkills(player["skills"], age=player["age"])
    r = PlayerEvaluator.rate_player(skills, player["throws"])
    if player["pos"] in ("sp", "rp"):
        value = max(r["sp"], r["rp"])
        return {"overall": value, "grade": overall_to_grade(value, "pitcher")}
    return {
        "overall": r["overall_player"],
        "grade": overall_to_grade(r["overall_player"], "hitter"),
    }


ABBR = {
    "contact": "CON",
    "power": "POW",
    "eye": "EYE",
    "speed": "SPD",
    "base_running": "BR",
    "bunting": "BUN",
    "durability": "DUR",
    "clutch": "CLU",
    "catching": "CA",
    "infield": "IF",
    "outfield": "OF",
    "arm": "ARM",
    "accuracy": "ACC",
    "strikes": "K",
    "ground_balls": "GB",
    "stamina": "STA",
    "recovery": "REC",
}


def print_roster(title: str, players: list[dict]) -> None:
    print(f"\n## {title}\n")
    hit = [s for s in SKILL_ORDER if s not in PITCH_SKILLS]
    hitters = [p for p in players if p["pos"] not in ("sp", "rp")]
    pitchers = [p for p in players if p["pos"] in ("sp", "rp")]
    head = (
        "| Player | Pos | Age | B/T | Ovr | " + " | ".join(ABBR[s] for s in hit) + " |"
    )
    print(head)
    print("|" + "---|" * (5 + len(hit)))
    for p in hitters:
        g = grades(p)
        print(
            f"| {p['name']} | {p['pos'].upper()} | {p['age']} | {p['bats']}/{p['throws']} | "
            f"{g['grade']} ({g['overall']}) | "
            + " | ".join(str(p["skills"][s]) for s in hit)
            + " |"
        )
    cols = PITCH_SKILLS + ["clutch"]
    print()
    print(
        "| Pitcher | Role | Age | T | Ovr | " + " | ".join(ABBR[s] for s in cols) + " |"
    )
    print("|" + "---|" * (5 + len(cols)))
    for p in pitchers:
        g = grades(p)
        print(
            f"| {p['name']} | {p['pos'].upper()} | {p['age']} | {p['throws']} | "
            f"{g['grade']} ({g['overall']}) | "
            + " | ".join(str(p["skills"][s]) for s in cols)
            + " |"
        )


TEAM_AREAS = ("lineup", "rotation", "bullpen", "defense", "power", "speed")


def as_record(p: dict):
    from src.player.player_record import PlayerRecord

    first, _, last = p["name"].partition(" ")
    return PlayerRecord(
        id=p["id"],
        first_name=first,
        last_name=last or first,
        bats=p["bats"],
        throws=p["throws"],
        position=p["pos"],
        skills=PlayerSkills(p["skills"], age=p["age"]),
    )


def team_report(players: list[dict], n_ref: int = 300) -> dict:
    """The welcome-page area grades for the team's 26 (13 hitters + 13
    pitchers with the most playing time), and where each would rank among
    generated 26-man rosters (percentile)."""
    from src.api.view_models.welcome import area_scores
    from src.league.offseason.draft_strategy import ratings

    if not hasattr(team_report, "_ref"):
        factory = TeamFactory(rng=random.Random(11))
        ref = {a: [] for a in TEAM_AREAS}
        for i in range(n_ref):
            t = factory.generate_team(city=f"Ref{i}", mascot="Sims", size=26)
            scores = area_scores([(p, ratings(p)) for p in t.players])
            for a in TEAM_AREAS:
                ref[a].append(scores[a])
        team_report._ref = ref
    ref = team_report._ref
    hit = [p for p in players if p["pos"] not in ("sp", "rp")][:13]
    pit = [p for p in players if p["pos"] in ("sp", "rp")][:13]
    recs = [as_record(p) for p in hit + pit]
    scores = area_scores([(r, ratings(r)) for r in recs])
    return {
        a: {
            "score": round(scores[a], 1),
            "grade": overall_to_grade(scores[a], f"team_{a}"),
            "pct": round(100 * sum(x < scores[a] for x in ref[a]) / len(ref[a])),
        }
        for a in TEAM_AREAS
    }


def export_season(rater: Rater, year: int, out: Path) -> None:
    """Write every club of a season, rated, for src/league/real_seasons.

    Players are lists of skills in SKILLS order to keep the file small.
    """
    from src.league.real_seasons import SKILLS

    teams = rater.d["Teams"]
    clubs = []
    for t in teams[teams["yearID"] == year].sort_values("teamID").itertuples():
        players = rater.roster(year, t.teamID)
        clubs.append(
            {
                "id": t.teamID,
                "name": t.name,
                "w": int(t.W),
                "l": int(t.L),
                "attendance": int(t.attendance or 0),
                "players": [
                    {
                        "first": p["first"],
                        "last": p["last"],
                        "age": p["age"],
                        "pos": p["pos"],
                        "bats": p["bats"],
                        "throws": p["throws"],
                        "skills": [p["skills"][s] for s in SKILLS],
                    }
                    for p in players
                ],
            }
        )
    payload = {"year": year, "source": "Lahman Baseball Database", "clubs": clubs}
    text = json.dumps(payload, separators=(",", ":"))
    # One club per line keeps diffs readable.
    text = text.replace(',{"id":', ',\n{"id":')
    out.write_text(text + "\n")
    print(f"Wrote {len(clubs)} clubs to {out}")


PLAYERS_FILE = "players.tsv.gz"


def export_clubs(teams: pd.DataFrame, out: Path) -> None:
    """Every club code the player file uses, with its latest name and the
    years it played, for the custom-team builder's club filter."""
    clubs = {}
    for team_id, rows in teams.groupby("teamID"):
        rows = rows.sort_values("yearID")
        clubs[team_id] = {
            "name": rows.iloc[-1]["name"],
            "first": int(rows["yearID"].min()),
            "last": int(rows["yearID"].max()),
        }
    out.write_text(json.dumps(clubs, indent=0, sort_keys=True) + "\n")
    print(f"Wrote {len(clubs)} clubs to {out}")


def export_players(rater: Rater, out: Path) -> None:
    """Write every real player-season worth picking, rated, for custom teams
    (src/league/real_seasons/players.py): one tab-separated line each, the
    skills in SKILLS order, gzipped to keep the repo small."""
    import gzip

    from src.league.real_seasons import SKILLS

    b = rater.d["Batting"]
    pa = (
        (b[["AB", "BB", "HBP", "SH", "SF"]].apply(pd.to_numeric, errors="coerce"))
        .fillna(0)
        .sum(axis=1)
    )
    pa = pa.groupby([b["playerID"], b["yearID"]]).sum()
    p = rater.d["Pitching"]
    outs = pd.to_numeric(p["IPouts"], errors="coerce").fillna(0)
    outs = outs.groupby([p["playerID"], p["yearID"]]).sum()
    keys = sorted(
        set(pa[pa >= MIN_PA].index) | set(outs[outs >= MIN_IPOUTS].index),
        key=lambda k: (k[1], k[0]),
    )
    a = rater.d["Appearances"]
    a = a.assign(order=range(len(a)))
    clubs = (
        a.sort_values("order")
        .groupby(["playerID", "yearID"])["teamID"]
        .agg(lambda t: "/".join(dict.fromkeys(t)))
    )
    head = [
        "id",
        "year",
        "first",
        "last",
        "born",
        "age",
        "pos",
        "bats",
        "throws",
        "teams",
    ]
    lines = ["\t".join(head + list(SKILLS))]
    for i, (pid, year) in enumerate(keys):
        r = rater.rate(pid, int(year))
        row = [pid, str(year), r["first"] or "", r["last"] or ""]
        row += [str(r["born"] or ""), str(r["age"])]
        row += [r["pos"], r["bats"], r["throws"], clubs.get((pid, year), "")]
        row += [str(r["skills"][s]) for s in SKILLS]
        lines.append("\t".join(row))
        if i % 10000 == 0:
            print(f"{i}/{len(keys)}", flush=True)
    with gzip.open(out, "wt", compresslevel=9) as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {len(keys)} player-seasons to {out}")
    export_clubs(rater.d["Teams"], out.parent / "clubs.json")


def lahman_dir() -> Path:
    """The Lahman parquet files that ship inside the pylahman package."""
    from importlib.util import find_spec

    spec = find_spec("pylahman")
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(
            "No Lahman data: run with `uv run --extra stats ...`, or pass --data DIR."
        )
    return Path(next(iter(spec.submodule_search_locations))) / "data"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--data",
        type=Path,
        help="Lahman parquet folder (default: the pylahman package's own)",
    )
    ap.add_argument("--teams", default="1961:NYA,2001:SEA,1986:NYN")
    ap.add_argument("--ref-teams", type=int, default=400)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--workload", choices=["modern", "era"], default="modern")
    ap.add_argument(
        "--export-season",
        type=int,
        help="Write every club of this season to src/league/real_seasons/data/",
    )
    ap.add_argument(
        "--export-players",
        action="store_true",
        help="Write every player-season (custom teams) to src/league/real_seasons/data/",
    )
    args = ap.parse_args()

    global WORKLOAD
    WORKLOAD = args.workload
    rater = Rater(args.data or lahman_dir(), args.ref_teams)
    if args.export_players:
        export_players(
            rater,
            Path(__file__).resolve().parent.parent
            / "src/league/real_seasons/data"
            / PLAYERS_FILE,
        )
        return
    if args.export_season:
        export_season(
            rater,
            args.export_season,
            Path(__file__).resolve().parent.parent
            / "src/league/real_seasons/data"
            / f"{args.export_season}.json",
        )
        return
    result = {}
    tnames = rater.d["Teams"].set_index(["yearID", "teamID"])["name"]
    for spec in args.teams.split(","):
        year, team = spec.split(":")
        year = int(year)
        players = rater.roster(year, team)
        for p in players:
            p.update(grades(p))
        title = f"{year} {tnames.loc[(year, team)]}"
        report = team_report(players)
        result[title] = {"team": report, "players": players}
        print_roster(title, players)
        print(
            "\nTeam vs generated 26-man rosters: "
            + ", ".join(
                f"{a} {r['grade']} ({r['pct']}th pct)" for a, r in report.items()
            )
        )
    if args.json:
        args.json.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
