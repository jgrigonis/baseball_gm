# Refactoring Resolver with WeightedChoice

## Summary of Changes

### Key Refactoring Steps

1. **Initialize WeightedChoice instances in `__init__`**
   - `self.pitch_outcome = WeightedChoice(rng=rng)`
   - `self.in_play_outcome = WeightedChoice(rng=rng)`
   - `self.double_steal_choice = WeightedChoice({...}, rng=rng)`
   - `self.first_and_third_choice = WeightedChoice({...}, rng=rng)`

2. **Extract weight setup into dedicated methods**
   - `_setup_pitch_outcome_weights()` - replaces `set_probs()`
   - `_setup_in_play_weights()` - replaces `set_in_play_probs()`

3. **Rename and simplify update methods**
   - `update_probs_for_X()` → `_modify_for_X()`
   - `update_in_play_probs_for_X()` → `_modify_in_play_for_X()`
   - Use WeightedChoice API instead of direct dict manipulation

4. **Simplify outcome determination**
   ```python
   # BEFORE
   self.set_probs()
   self.update_probs(game)
   return self.random_event(self.probs)
   
   # AFTER
   self.pitch_outcome.reset()
   self._apply_pitch_modifiers(game)
   return self.pitch_outcome.choose()
   ```

5. **Delete obsolete methods**
   - `random_event()` - replaced by `WeightedChoice.choose()`
   - `set_probs()` - replaced by `_setup_pitch_outcome_weights()`
   - `update_probs()` - replaced by `_apply_pitch_modifiers()`
   - Similar for in-play methods

---

## Benefits

### 1. **Clearer Intent**
```python
# BEFORE - unclear what's happening
self.probs["strike"] = int(self.probs["strike"] * 0.97)

# AFTER - explicit action
self.pitch_outcome.multiply("strike", 0.97)
```

### 2. **Better Separation of Concerns**
- WeightedChoice handles probability math
- Resolver focuses on game logic
- Easier to test each independently

### 3. **Reduced Boilerplate**
```python
# BEFORE - manual dict manipulation
if self.probs["wild_pitch"] != 0:
    self.probs["wild_pitch"] -= accuracy - 50

# AFTER - automatic handling
self.pitch_outcome.add("wild_pitch", -(accuracy - 50))
```

### 4. **Safer Operations**
- No need to check if key exists before modifying
- Automatic clamping of negative values to 0
- Clear separation between base and current weights

### 5. **Easier to Debug**
```python
# Can inspect probabilities at any time
current_weights = self.pitch_outcome.get_weights()
current_probs = self.pitch_outcome.get_probabilities()
```

### 6. **More Maintainable**
- Clear structure: reset → modify → choose
- Each modifier method is focused on one aspect
- Easy to add/remove modifiers

---

## Migration Strategy

### Phase 1: Add WeightedChoice alongside existing code
```python
def __init__(self, rng):
    self.rng = rng
    self.logger = logging.getLogger("game.resolver")
    
    # NEW: Add WeightedChoice instances
    self.pitch_outcome = WeightedChoice(rng=rng)
    self._setup_pitch_outcome_weights()
```

### Phase 2: Refactor one outcome type at a time
Start with pitch outcomes, verify tests pass, then move to in-play outcomes.

### Phase 3: Clean up old code
Once all outcomes use WeightedChoice, delete:
- `self.probs` and `self.in_play_probs` attributes
- `random_event()`, `set_probs()`, `update_probs()` methods

---

## Example Comparison

### Pitch Outcome Determination

**BEFORE (69 lines):**
```python
def _determine_pitch_outcome(self, intent, game) -> str:
    self.logger.trace("_determine_pitch_outcome")
    self.set_probs()
    self.update_probs(game)
    return self.random_event(self.probs)

def set_probs(self):
    self.probs = {
        "ball": 10800,
        "foul": 5100,
        # ... 8 more outcomes
    }

def update_probs(self, game):
    self.update_probs_for_bases(game.bases)
    self.update_probs_for_situation(game.situation, game.current_batter.player)
    self.update_probs_for_count(game.count)
    self.update_probs_for_batter(game.current_batter.player)
    self.update_probs_for_pitcher(game.current_pitcher)

def update_probs_for_bases(self, bases: Bases):
    if bases.is_empty:
        self.probs["illegal_pitch"] = 10
    else:
        self.probs["balk"] = 10
        self.probs["ball"] = int(self.probs["ball"] * 1.03)
        self.probs["strike"] = int(self.probs["strike"] * 0.97)
        # ... more mutations
```

**AFTER (cleaner structure):**
```python
def _determine_pitch_outcome(self, intent, game) -> str:
    self.logger.trace("_determine_pitch_outcome")
    self.pitch_outcome.reset()
    self._apply_pitch_modifiers(game)
    return self.pitch_outcome.choose()

def _apply_pitch_modifiers(self, game):
    """Single orchestration method."""
    self._modify_for_bases(game.bases)
    self._modify_for_situation(game.situation, game.current_batter.player)
    self._modify_for_count(game.count)
    self._modify_for_batter(game.current_batter.player)
    self._modify_for_pitcher(game.current_pitcher)

def _modify_for_bases(self, bases: Bases):
    """Focused modifier - clear intent."""
    if bases.is_empty:
        self.pitch_outcome.set("illegal_pitch", 10)
    else:
        self.pitch_outcome.set("balk", 10)
        self.pitch_outcome.multiply("ball", 1.03)
        self.pitch_outcome.multiply("strike", 0.97)
        # ... more operations
```

---

## Pattern to Follow

For each probability-based decision:

1. **Initialize** the WeightedChoice in `__init__`
2. **Set base weights** in a `_setup_X_weights()` method
3. **Reset** before each use: `choice.reset()`
4. **Apply modifiers** with `multiply()`, `add()`, `set()`
5. **Choose** the outcome: `choice.choose()`

This creates a clear, predictable flow for all probability decisions.
