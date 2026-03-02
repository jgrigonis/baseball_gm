Already  covering most of the “headline” outcomes.
here is **everything that can legally happen on a single pitch**

here are some additional events worth considering, 
grouped by type. This should plug in nicely with the 
stats/engine design.

---

## Pitch / Pitcher-related (no contact required)

These can happen even if the batter doesn’t swing.

* **intentional_ball** (IBB pitch, or auto-walk)
* **pitchout**
* **clock_violation** (pitch timer)
* **illegal_pitch** (results in ball)
* **foreign_substance_ejection** (rare, but real)
* **pitcher_disengagement** (step-off attempt)
* **pitcher_pickoff_attempt** (no out recorded)

---

## Batter-related (no fair ball in play)

Some of these end the plate appearance, some don’t.

* **strikeout_swinging**
* **strikeout_looking**
* **foul_tip** (caught → strikeout; uncaught → strike)
* **batter_interference** (rare but pitch-based)
* **catcher_interference** (awarded first base)
* **hit_by_pitch_strike** (HBP in strike zone = strike, not HBP)

---

## Ball-in-play variants 
(more granular than “ground_out” / “fly_out”)

If you want more realism or better stat tracking:

* **line_out**
* **pop_out** (infield fly)
* **infield_fly_rule** (special case of pop-up)
* **force_out**
* **tag_out**
* **reached_on_error**
* **reached_on_interference**
* **inside_the_park_home_run**
* **ground_rule_double**
* **fan_interference**

---

## Base running events triggered by the pitch

These are big ones if you want emergent chaos 🙂

* **advance_on_wild_pitch**
* **advance_on_passed_ball**
* **defensive_indifference**
* **runner_interference**
* **runner_hit_by_batted_ball**
* **appeal_play** (missed base on live ball)
* **overslide_out**
* **bases_loaded_walk_run**
* **bases_loaded_hbp_run**

---

## Outs not directly tied to the batter

Still occur *during* the pitch sequence.

* **pickoff_error**
* **steal_error**
* **double_steal**
* **delayed_steal**
* **run_down_out**
* **appeal_strikeout** (check swing appeal)

---

## Rare / edge-case chaos (optional but fun)

Great for a sim engine if you want “baseball weirdness.”

* **four_strike_strikeout** (foul bunt w/ two strikes)
* **dropped_third_strike_advance**
* **uncaught_third_strike_out**
* **batted_ball_hits_runner**
* **batted_ball_hits_umpire**
* **ball_lodged_in_equipment**
* **spectator_interference_home_run**
* **walk_off_event** (contextual)

---

## Design tip (based on your code direction)

Instead of a flat list, consider tagging events:

```python
event = {
    "name": "wild_pitch",
    "ends_at_bat": False,
    "in_play": False,
    "can_advance_runners": True,
    "records_out": False
}
```

That makes things like:

* “wild pitch + strike”
* “foul tip strikeout”
* “ground ball + double play”

fall out naturally.

---

* Normalize these into a **clean enum**
* Help you assign **realistic probabilities**
* Or map each event to **stat updates** 
(`batting`, `pitching`, `fielding`, `baserunning`)
