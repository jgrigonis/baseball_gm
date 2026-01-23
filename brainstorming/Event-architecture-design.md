# Event Architecture for Pre-Pitch and Concurrent Events

## Problem Statement

We need to handle three types of events in the baseball simulation:
1. **Pre-pitch events**: Pickoffs, pickoff attempts (happen BEFORE the pitch)
2. **Concurrent events**: Steals, caught stealing (happen DURING the pitch)
3. **Post-pitch events**: The existing hit/out/walk outcomes (happen AFTER the pitch)

## Proposed Architecture

Modify the `Resolver.resolve()` method to handle multiple phases:

```python
def resolve(self, intent: GameIntent, game) -> List[GameEvent]:
    """
    Resolve an intent into one or more GameEvents.
    
    For PitchIntent, this happens in three phases:
    1. Pre-pitch phase (pickoffs, etc.)
    2. Pitch phase (pitch thrown + outcome)
    3. Concurrent phase (steals attempted during pitch)
    """
    if isinstance(intent, PitchIntent):
        events = []
        
        # Phase 1: Pre-pitch events
        events.extend(self._resolve_pre_pitch_events(intent, game))
        
        # Phase 2: The pitch itself
        events.extend(self._resolve_pitch(intent, game))
        
        # Phase 3: Concurrent events (steals)
        events.extend(self._resolve_concurrent_events(intent, game))
        
        return events
    
    raise RuntimeError(f"Unhandled intent type: {type(intent).__name__}")
```

### Phase Breakdown

#### Phase 1: Pre-Pitch Events

These happen before the pitch is thrown:

```python
def _resolve_pre_pitch_events(self, intent: PitchIntent, game) -> List[GameEvent]:
    """
    Resolve events that happen before the pitch.
    
    Examples:
    - Pickoff attempts
    - Balks (some types)
    """
    events = []
    
    # Only attempt pickoffs if runners are on base
    if game.bases.is_empty:
        return events
    
    # Decide if pitcher attempts pickoff
    if self._should_attempt_pickoff(intent, game):
        base = self._select_pickoff_target(game)
        pickoff_result = self._resolve_pickoff_attempt(base, game)
        events.extend(pickoff_result)
        
        # If pickoff successful, runner is out
        # If unsuccessful, continue to pitch
    
    return events

def _should_attempt_pickoff(self, intent, game) -> bool:
    """Decide if pitcher attempts a pickoff"""
    # Higher probability with:
    # - Runner on first
    # - Runner with high steal probability
    # - Good pickoff pitcher
    
    if not game.bases.occupied_map():
        return False
    
    # Base probability
    pickoff_prob = 0.02  # 2% chance per pitch
    
    # TODO: Adjust based on:
    # - Runner speed/steal tendency
    # - Pitcher pickoff skill
    # - Game situation (close game, late innings)
    
    return self.rng.random() < pickoff_prob

def _select_pickoff_target(self, game) -> int:
    """Select which base to attempt pickoff"""
    occupied = game.bases.occupied_map()
    
    # Prioritize first base (most common)
    if FIRST in occupied:
        return FIRST
    elif SECOND in occupied:
        return SECOND
    elif THIRD in occupied:
        return THIRD
    
    return None

def _resolve_pickoff_attempt(self, base: int, game) -> List[GameEvent]:
    """
    Resolve a pickoff attempt.
    
    Outcomes:
    - Successful pickoff (runner out)
    - Failed pickoff (runner safe, maybe advances)
    - Throwing error (runner advances)
    """
    events = []
    runner = game.bases.runner_on(base)
    
    if not runner:
        return events
    
    events.append(PickoffAttemptEvent(base=base, runner_id=runner))
    
    # Determine outcome
    success_prob = 0.15  # 15% successful pickoff rate
    error_prob = 0.05    # 5% throwing error rate
    
    r = self.rng.random()
    
    if r < success_prob:
        # Successful pickoff
        events.append(PickoffSuccessEvent(base=base, runner_id=runner))
        events.append(OutRecordedEvent(reason="pickoff"))
        events.append(RunnerRemovedEvent(
            runner_id=runner,
            from_base=base,
            reason="pickoff"
        ))
    elif r < success_prob + error_prob:
        # Throwing error - runner advances
        events.append(PickoffErrorEvent(base=base, runner_id=runner))
        events.append(RunnerAdvancedEvent(
            runner_id=runner,
            from_base=base,
            to_base=min(base + 1, HOME),
            reason="pickoff_error"
        ))
    else:
        # Runner safe, no advancement
        events.append(PickoffFailedEvent(base=base, runner_id=runner))
    
    return events
```

#### Phase 2: The Pitch (Existing)

Your existing `_resolve_pitch` method handles this.

#### Phase 3: Concurrent Events (Steals)

These happen during the pitch:

```python
def _resolve_concurrent_events(self, intent: PitchIntent, game) -> List[GameEvent]:
    """
    Resolve events that happen concurrently with the pitch.
    
    Examples:
    - Stolen base attempts
    - Caught stealing
    """
    events = []
    
    # Only attempt steals if runners are on base
    if game.bases.is_empty:
        return events
    
    # Check each occupied base for steal attempt
    occupied = sorted(game.bases.occupied_map().keys())
    
    for base in occupied:
        if self._should_attempt_steal(base, intent, game):
            steal_result = self._resolve_steal_attempt(base, game)
            events.extend(steal_result)
    
    return events

def _should_attempt_steal(self, from_base: int, intent, game) -> bool:
    """Decide if runner attempts to steal"""
    # Can't steal home on most pitches (rare)
    if from_base == THIRD:
        return self.rng.random() < 0.001  # Very rare
    
    # Can't steal if next base occupied (usually)
    next_base = from_base + 1
    if game.bases.runner_on(next_base):
        return False
    
    # Base steal probability
    if from_base == FIRST:
        steal_prob = 0.08  # 8% chance
    elif from_base == SECOND:
        steal_prob = 0.02  # 2% chance
    else:
        steal_prob = 0.001
    
    # TODO: Adjust based on:
    # - Runner speed
    # - Pitcher delivery time
    # - Catcher arm strength
    # - Game situation
    # - Count (more likely on 3-2, less on 0-2)
    
    return self.rng.random() < steal_prob

def _resolve_steal_attempt(self, from_base: int, game) -> List[GameEvent]:
    """
    Resolve a steal attempt.
    
    Outcomes:
    - Successful steal
    - Caught stealing
    """
    events = []
    runner = game.bases.runner_on(from_base)
    to_base = from_base + 1
    
    if not runner:
        return events
    
    events.append(StealAttemptEvent(
        runner_id=runner,
        from_base=from_base,
        to_base=to_base
    ))
    
    # Determine success
    # Historical success rate: ~75% for second base, ~80% for third
    if from_base == FIRST:
        success_prob = 0.75
    elif from_base == SECOND:
        success_prob = 0.80
    elif from_base == THIRD:
        success_prob = 0.85
    else:
        success_prob = 0.50
    
    # TODO: Adjust based on runner speed, catcher arm, pitcher
    
    if self.rng.random() < success_prob:
        # Successful steal
        events.append(StolenBaseEvent(
            runner_id=runner,
            from_base=from_base,
            to_base=to_base
        ))
        events.append(RunnerAdvancedEvent(
            runner_id=runner,
            from_base=from_base,
            to_base=to_base,
            reason="stolen_base"
        ))
    else:
        # Caught stealing
        events.append(CaughtStealingEvent(
            runner_id=runner,
            from_base=from_base,
            to_base=to_base
        ))
        events.append(OutRecordedEvent(reason="caught_stealing"))
        events.append(RunnerRemovedEvent(
            runner_id=runner,
            from_base=from_base,
            reason="caught_stealing"
        ))
    
    return events
```

### New Event Types Needed

```python
# Pre-pitch events
class PickoffAttemptEvent(GameEvent):
    """Pitcher attempts to pick off runner"""
    def __init__(self, base: int, runner_id: str):
        self.base = base
        self.runner_id = runner_id

class PickoffSuccessEvent(GameEvent):
    """Successful pickoff"""
    pass

class PickoffFailedEvent(GameEvent):
    """Failed pickoff attempt, runner safe"""
    pass

class PickoffErrorEvent(GameEvent):
    """Throwing error on pickoff"""
    pass

# Concurrent events
class StealAttemptEvent(GameEvent):
    """Runner attempts to steal"""
    def __init__(self, runner_id: str, from_base: int, to_base: int):
        self.runner_id = runner_id
        self.from_base = from_base
        self.to_base = to_base

class StolenBaseEvent(GameEvent):
    """Successful stolen base"""
    pass

class CaughtStealingEvent(GameEvent):
    """Runner caught stealing"""
    pass
```

## Edge Cases to Handle

### 1. Pickoff Ending the Inning
```python
def _resolve_pre_pitch_events(self, intent, game) -> List[GameEvent]:
    events = []
    
    # If pickoff results in third out, don't throw the pitch!
    pickoff_events = self._attempt_pickoff_if_applicable(intent, game)
    events.extend(pickoff_events)
    
    # Check if inning ended
    outs_recorded = sum(1 for e in pickoff_events if isinstance(e, OutRecordedEvent))
    if game.outs + outs_recorded >= 3:
        # Inning over, don't continue to pitch
        return events
    
    return events
```

### 2. Multiple Runners Stealing (Double Steal)
```python
def _resolve_concurrent_events(self, intent, game) -> List[GameEvent]:
    """Handle multiple simultaneous steal attempts"""
    events = []
    
    # Collect all steal attempts first
    steal_attempts = []
    for base in sorted(game.bases.occupied_map().keys()):
        if self._should_attempt_steal(base, intent, game):
            steal_attempts.append(base)
    
    # If multiple steals, it's a double steal - different probabilities
    if len(steal_attempts) > 1:
        return self._resolve_double_steal(steal_attempts, game)
    
    # Single steal
    for base in steal_attempts:
        events.extend(self._resolve_steal_attempt(base, game))
    
    return events
```

### 3. Steal on Strikeout/Walk
Steals can happen even when the batter strikes out or walks. The concurrent events should still process:

```python
# In _resolve_pitch, after determining outcome:
# Don't early return for strikeouts/walks - concurrent events can still happen
```

### 4. Caught Stealing Ending Inning
If caught stealing is the third out, the pitch outcome doesn't matter for runs scoring:

```python
def _resolve_concurrent_events(self, intent, game) -> List[GameEvent]:
    events = []
    
    # ... steal attempts ...
    
    # Check if third out was recorded
    outs_in_events = sum(1 for e in events if isinstance(e, OutRecordedEvent))
    if game.outs + outs_in_events >= 3:
        # Inning over - any runs that would have scored don't count
        # Need to filter out scoring plays that happened after the out
        pass
    
    return events
```

## Integration with Game Loop

Your game loop would look like:

```python
class Game:
    def process_pitch(self):
        # Create pitch intent
        intent = PitchIntent(
            pitcher_id=self.current_pitcher,
            batter_id=self.current_batter,
            pitch_type="fastball"
        )
        
        # Resolver handles all three phases
        events = self.resolver.resolve(intent, self)
        
        # Apply all events
        for event in events:
            self.apply(event)
            
            # Check for inning end after each event
            if self.outs >= 3:
                break
```

## Benefits of This Architecture

1. **Clean separation**: Pre-pitch, pitch, and concurrent events are clearly separated
2. **Flexible**: Easy to add new event types to each phase
3. **Realistic**: Mirrors actual baseball flow
4. **Testable**: Each phase can be tested independently
5. **Maintains existing code**: Your current `_resolve_pitch` stays mostly intact

## Alternative: Event Flags on Intent

If you want more control, you could add flags to the intent:

```python
class PitchIntent(GameIntent):
    def __init__(self, pitcher_id, batter_id, pitch_type,
                 attempt_pickoff=None,  # None = auto-decide, or specify base
                 runner_steal_attempts=None):  # List of bases attempting steals
        self.pitcher_id = pitcher_id
        self.batter_id = batter_id
        self.pitch_type = pitch_type
        self.attempt_pickoff = attempt_pickoff
        self.runner_steal_attempts = runner_steal_attempts or []
```

This gives you explicit control over what happens, which might be useful for:
- AI opponents making strategic decisions
- Replaying historical games
- Testing specific scenarios
