
BEFORE PITCH (Pre-pitch phase):
├── Managers decide tactical plays:
│   ├── Offense: steal? bunt? hit-and-run?
│   └── Defense: pitch-out? intentional walk?
├── Runners take their leads
├── Pitcher may attempt pickoff
│   ├── If pickoff: resolve it, end pre-pitch phase
│   └── If no pickoff or failed: continue
└── Pitcher begins delivery

DURING PITCH (Pitch phase):
├── Pitch thrown (affected by tactical situation)
├── Batter action: swing/take/bunt (affected by situation)
└── Initial outcome: ball/strike/foul/in_play

IF BALL IN PLAY (Ball in play phase):
├── Fair or Foul determination
├── Batted ball type (ground/fly/line - implicit in outcome)
├── Defensive plays executed
│   ├── Accounting for all runners
│   ├── Force plays, tag plays, etc.
│   └── Runners advance based on hit type and defense
└── Update game state (NO separate steal resolution)

IF BALL NOT IN PLAY (Post-pitch phase):
├── Ball/strike count updated
├── IF steal attempt was on:
│   ├── Resolve steal based on pitch outcome
│   └── Runner safe/out
└── Update game state

