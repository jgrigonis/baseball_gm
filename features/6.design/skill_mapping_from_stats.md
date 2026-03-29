

# 🟢 Tier 1 — Directly derivable (high confidence)

These map cleanly from standard stat lines or commonly available advanced stats.

### Pitching

* **accuracy → BB% (walk rate)**

  * Lower BB% = higher accuracy
  * Easy normalization vs league avg

* **strikes → K% or K-BB%**

  * K% = raw “stuff”
  * K-BB% = better overall dominance signal

* **ground_balls → GB%**

  * Direct stat (FanGraphs / Statcast)

---

### Hitting

* **power → ISO (SLG - AVG)**

  * Gold standard
  * HR/PA also works but noisier

* **contact → K% (inverse)**

  * Lower K% = higher contact

* **eye → BB% or BB/K**

  * BB/K is nice because it stabilizes approach

---

### Speed / Baserunning

* **speed → SB attempts + triples + Statcast sprint speed**

  * Best: sprint speed
  * Fallback: SB/PA + 3B rate

* **base_running → BsR (FanGraphs)**

  * If unavailable: SB success rate + advancement metrics

---

# 🟡 Tier 2 — Derivable with modeling / proxies

These require combining stats or making assumptions.

### Pitching

* **stamina → IP per start / pitches per start**

  * Or total IP for relievers vs appearances

* **recovery → appearances + days rest patterns**

  * Hard from raw stat lines alone
  * Needs game logs ideally

---

### General

* **durability → games played / IP / PA**

  * Or % of team games played

* **clutch → WPA or Clutch stat (FanGraphs)**

  * Very noisy year-to-year (beware)

---

### Bunting

* **bunting → sacrifice bunts (SH)**

  * But:

    * Extremely era + team dependent
    * Weak signal for actual skill

---

# 🔴 Tier 3 — Weak / indirect / missing from stat lines

These need advanced tracking or are basically hidden variables.

### Defense

* **infield / outfield → OAA, DRS, UZR**

  * Modern era: decent
  * Historical: gets rough fast

* **catching → framing (FRM), caught stealing %**

  * Framing is essential but only recent data

* **arm → outfield assists / pop time (catchers)**

  * Very noisy proxy

---

# 🧠 Core problem: scaling to your 1–100 system

You need a normalization layer:

### Option A — Z-score → rating

```text
rating = 50 + (player_stat - league_avg) / league_std * scale
```

* Scale ~10–15 works well
* Clamp to [1, 100]

---

### Option B — Percentiles (cleaner)

```text
rating = percentile * 100
```

* Much more stable across eras
* Strongly recommended

---

# ⚾ Example mapping (clean version)

| Skill        | Metric                  |
| ------------ | ----------------------- |
| accuracy     | BB% (inverse)           |
| strikes      | K% or K-BB%             |
| ground_balls | GB%                     |
| stamina      | IP/start                |
| recovery     | appearances/rest        |
| durability   | games played / IP       |
| power        | ISO                     |
| contact      | K% (inverse)            |
| eye          | BB%                     |
| speed        | sprint speed / SB rate  |
| base_running | BsR                     |
| bunting      | SH                      |
| clutch       | WPA / Clutch            |
| infield      | OAA/DRS (infield only)  |
| outfield     | OAA/DRS (outfield only) |
| catching     | framing + CS%           |
| arm          | assists / pop time      |

---

# ⚠️ Big caveats

### 1. Era adjustment is mandatory

* League averages shift a lot (e.g., K% explosion post-2015)
* Always normalize **within season**

---

### 2. Single-season noise is real

* Especially for:

  * clutch
  * defense
  * bunting
* Better approach:

  > Blend season + career (e.g., 70/30 or 50/50)

---

### 3. Some skills are *latent*, not observable

You're really inferring:

* arm strength
* defensive range
* “true” contact ability vs outcomes

Stat lines = outputs, not pure skills.

---

# 💡 If you want this to feel *really good*

Do this:

### 1. Use percentiles within season

### 2. Blend:

```text
final = 0.7 * season + 0.3 * 3-year average
```

### 3. Add noise

* ±3–5 randomness so players don’t feel identical

---

# 🔥 Practical verdict

* **~70% of your system maps cleanly** → totally viable
* **~20% needs reasonable proxies** → still good
* **~10% is “game feel” territory** → you fake it


