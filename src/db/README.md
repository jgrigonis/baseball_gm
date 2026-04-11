src/db/README.md

Tables model data.
Repositories model questions.


If you ask:

“Give me this player’s season stats” → one repo

“Insert game stats” → one repo

“Recover pitcher stamina over rest days” → one repo

Even if that means touching 3 tables.

One gameplay concern = one repository
Query-driven design


Game logs are facts.
Stats objects are views.
Repositories are translators.

The database is now the source of truth.
Stats, SeasonStats, and CareerStats are projections.

Domain objects should not fetch themselves.
Repositories fetch. Domain objects aggregate.
