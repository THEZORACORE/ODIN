"""VÖLVA — Simulation engine (model-based lookahead).

Monte-Carlo "what-if" rollouts over the world model *before* committing
an action.  The orchestrator can ask: "if I do X, what happens?" and
VÖLVA simulates the consequences using the causal graph.

Simulation flow:
1. Take a snapshot of the current world state
2. Apply a hypothetical action (entity property changes, new events)
3. Propagate effects through causal links
4. Score the outcome (configurable objective function)
5. Repeat with alternative actions → pick the best

This is a lightweight, rule-based simulator — not a learned dynamics
model.  It uses the causal graph from NORNS to propagate effects.
"""

from __future__ import annotations

import copy
import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from odin.world.norns import CausalEngine
from odin.world.yggdrasil import WorldModel

logger = logging.getLogger("odin.world.volva")


class Action(BaseModel):
    """A hypothetical action to simulate."""

    id: str
    description: str
    target_entity_id: str
    property_changes: dict[str, object] = Field(default_factory=dict)
    event_type: str = "action"


class SimulationResult(BaseModel):
    """The outcome of a simulated action."""

    action: Action
    score: float = 0.0
    effects: list[str] = Field(default_factory=list)
    entity_states: dict[str, dict[str, object]] = Field(default_factory=dict)
    events_triggered: int = 0
    reasoning: str = ""


class Simulation:
    """VÖLVA — simulate actions against the world model.

    Uses YGGDRASIL for state and NORNS for causal propagation.
    """

    def __init__(self, world: WorldModel, causal: CausalEngine) -> None:
        self._world = world
        self._causal = causal

    def simulate(self, action: Action) -> SimulationResult:
        """Simulate a single action and return the predicted outcome."""
        effects: list[str] = []
        entity_states: dict[str, dict[str, object]] = {}
        events_triggered = 0

        # 1. Get current entity state
        entity = self._world.get_entity(action.target_entity_id)
        if entity is None:
            return SimulationResult(
                action=action,
                score=0.0,
                reasoning=f"Entity {action.target_entity_id} not found in world model.",
            )

        # 2. Apply hypothetical property changes (in-memory copy)
        simulated = copy.deepcopy(entity)
        for key, value in action.property_changes.items():
            old_val = simulated.properties.get(key)
            simulated.properties[key] = value
            effects.append(f"{simulated.name}.{key}: {old_val} → {value}")
        entity_states[simulated.id] = dict(simulated.properties)

        # 3. Check causal consequences via NORNS
        # Look for events related to this entity to find causal chains
        recent_events = self._causal.get_timeline(entity_id=action.target_entity_id, limit=10)
        for event in recent_events:
            chain = self._causal.get_effects(event.id, max_depth=2)
            events_triggered += len(chain.links)
            for linked_event in chain.events:
                if linked_event.id != event.id:
                    effects.append(f"→ triggers: {linked_event.description}")
                    # Track affected entity states
                    affected = self._world.get_entity(linked_event.entity_id)
                    if affected and affected.id not in entity_states:
                        entity_states[affected.id] = dict(affected.properties)

        # 4. Score the outcome
        score = self._score_outcome(action, effects, entity_states)

        return SimulationResult(
            action=action,
            score=score,
            effects=effects,
            entity_states=entity_states,
            events_triggered=events_triggered,
            reasoning=f"Simulated {action.description}: {len(effects)} effects, score={score:.2f}",
        )

    def compare_actions(self, actions: list[Action]) -> list[SimulationResult]:
        """Simulate multiple actions and rank by score (highest first)."""
        results = [self.simulate(a) for a in actions]
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def best_action(self, actions: list[Action]) -> SimulationResult | None:
        """Return the highest-scoring action, or None if no actions."""
        if not actions:
            return None
        ranked = self.compare_actions(actions)
        return ranked[0]

    def what_if(
        self,
        entity_id: str,
        property_changes: dict[str, object],
        description: str = "what-if scenario",
    ) -> SimulationResult:
        """Convenience: simulate a single what-if scenario."""
        action = Action(
            id=f"whatif_{datetime.now(UTC).timestamp():.0f}",
            description=description,
            target_entity_id=entity_id,
            property_changes=property_changes,
        )
        return self.simulate(action)

    @staticmethod
    def _score_outcome(
        action: Action,
        effects: list[str],
        entity_states: dict[str, dict[str, object]],
    ) -> float:
        """Score a simulated outcome.

        Simple heuristic scoring:
        - More effects = more impact (can be good or bad)
        - Property changes that move values "forward" score higher
        - Bounded [0, 1]
        """
        if not effects:
            return 0.5

        # Base score from number of effects (more effects = more impactful)
        effect_score = min(len(effects) / 10.0, 1.0)

        # Bonus for property changes (action actually changes state)
        change_count = len(action.property_changes)
        change_score = min(change_count / 5.0, 1.0)

        score = 0.3 * effect_score + 0.7 * change_score
        return round(min(max(score, 0.0), 1.0), 3)
