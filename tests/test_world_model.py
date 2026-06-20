"""Tests for the world model subsystem (Phase 7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from odin.world.norns import CausalEngine, CausalLink, TimelineEvent
from odin.world.volva import Action, Simulation
from odin.world.yggdrasil import Entity, Relation, WorldModel

# ---------------------------------------------------------------------------
# YGGDRASIL (7.1) — typed knowledge graph
# ---------------------------------------------------------------------------


class TestWorldModel:
    @pytest.fixture()
    def wm(self, tmp_path: Path) -> WorldModel:
        m = WorldModel(data_dir=str(tmp_path))
        yield m
        m.close()

    def test_add_and_get_entity(self, wm: WorldModel) -> None:
        e = Entity(id="e1", entity_type="service", name="auth-api")
        wm.add_entity(e)
        got = wm.get_entity("e1")
        assert got is not None
        assert got.name == "auth-api"

    def test_update_properties(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="e1", entity_type="service", name="api", properties={"version": 1}))
        updated = wm.update_properties("e1", {"version": 2, "healthy": True})
        assert updated is not None
        assert updated.properties["version"] == 2
        assert updated.properties["healthy"] is True

    def test_find_entities(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="e1", entity_type="service", name="auth-api"))
        wm.add_entity(Entity(id="e2", entity_type="database", name="postgres"))
        wm.add_entity(Entity(id="e3", entity_type="service", name="user-api"))

        services = wm.find_entities(entity_type="service")
        assert len(services) == 2

        found = wm.find_entities(name_contains="auth")
        assert len(found) == 1
        assert found[0].name == "auth-api"

    def test_remove_entity(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="e1", entity_type="service", name="api"))
        assert wm.remove_entity("e1")
        assert wm.get_entity("e1") is None

    def test_relations(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="e1", entity_type="service", name="api"))
        wm.add_entity(Entity(id="e2", entity_type="database", name="db"))
        wm.add_relation(Relation(source_id="e1", target_id="e2", relation_type="depends_on"))

        rels = wm.get_relations("e1", direction="outgoing")
        assert len(rels) == 1
        assert rels[0].relation_type == "depends_on"

        incoming = wm.get_relations("e2", direction="incoming")
        assert len(incoming) == 1

    def test_neighbors(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="a", entity_type="t", name="A"))
        wm.add_entity(Entity(id="b", entity_type="t", name="B"))
        wm.add_entity(Entity(id="c", entity_type="t", name="C"))
        wm.add_relation(Relation(source_id="a", target_id="b", relation_type="uses"))
        wm.add_relation(Relation(source_id="b", target_id="c", relation_type="calls"))

        n = wm.neighbors("a", max_depth=2)
        names = [e.name for e, _ in n]
        assert "B" in names
        assert "C" in names

    def test_stats(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="e1", entity_type="service", name="api"))
        s = wm.stats()
        assert s["entities"] == 1
        assert s["relations"] == 0

    def test_snapshot(self, wm: WorldModel) -> None:
        wm.add_entity(Entity(id="e1", entity_type="service", name="api"))
        snap = wm.snapshot()
        assert len(snap["entities"]) == 1
        assert "stats" in snap


# ---------------------------------------------------------------------------
# NORNS (7.2) — causal/temporal reasoning
# ---------------------------------------------------------------------------


class TestCausalEngine:
    @pytest.fixture()
    def norns(self, tmp_path: Path) -> CausalEngine:
        n = CausalEngine(data_dir=str(tmp_path))
        yield n
        n.close()

    def test_record_event(self, norns: CausalEngine) -> None:
        e = TimelineEvent(id="ev1", entity_id="svc1", event_type="deploy", description="Deployed v2")
        norns.record_event(e)
        timeline = norns.get_timeline(entity_id="svc1")
        assert len(timeline) == 1
        assert timeline[0].description == "Deployed v2"

    def test_causal_link(self, norns: CausalEngine) -> None:
        norns.record_event(TimelineEvent(id="ev1", entity_id="s1", event_type="deploy", description="Deploy"))
        norns.record_event(TimelineEvent(id="ev2", entity_id="s1", event_type="error", description="Error 500"))
        norns.add_causal_link(CausalLink(cause_event_id="ev1", effect_event_id="ev2", strength=0.9))

        causes = norns.get_causes("ev2")
        assert len(causes.events) == 2
        assert len(causes.links) == 1
        assert causes.total_strength > 0

    def test_causal_chain(self, norns: CausalEngine) -> None:
        norns.record_event(TimelineEvent(id="a", entity_id="s1", event_type="change", description="Config change"))
        norns.record_event(TimelineEvent(id="b", entity_id="s1", event_type="restart", description="Service restart"))
        norns.record_event(TimelineEvent(id="c", entity_id="s1", event_type="outage", description="Outage"))
        norns.add_causal_link(CausalLink(cause_event_id="a", effect_event_id="b"))
        norns.add_causal_link(CausalLink(cause_event_id="b", effect_event_id="c"))

        chain = norns.get_causes("c", max_depth=5)
        event_ids = [e.id for e in chain.events]
        assert "a" in event_ids
        assert "b" in event_ids

    def test_get_effects(self, norns: CausalEngine) -> None:
        norns.record_event(TimelineEvent(id="root", entity_id="s1", event_type="deploy", description="Deploy"))
        norns.record_event(TimelineEvent(id="eff1", entity_id="s1", event_type="load", description="Load spike"))
        norns.add_causal_link(CausalLink(cause_event_id="root", effect_event_id="eff1"))

        effects = norns.get_effects("root")
        assert len(effects.links) == 1

    def test_forecast(self, norns: CausalEngine) -> None:
        for i in range(5):
            norns.record_event(TimelineEvent(id=f"e{i}", entity_id="s1", event_type="deploy", description=f"Deploy {i}"))
        norns.record_event(TimelineEvent(id="e5", entity_id="s1", event_type="error", description="Error"))

        f = norns.forecast("s1")
        assert f.confidence > 0
        assert "deploy" in f.prediction.lower()

    def test_forecast_no_data(self, norns: CausalEngine) -> None:
        f = norns.forecast("nonexistent")
        assert f.confidence == 0.0

    def test_stats(self, norns: CausalEngine) -> None:
        norns.record_event(TimelineEvent(id="e1", entity_id="s1", event_type="t", description="d"))
        s = norns.stats()
        assert s["events"] == 1


# ---------------------------------------------------------------------------
# VÖLVA (7.3) — simulation
# ---------------------------------------------------------------------------


class TestSimulation:
    @pytest.fixture()
    def sim(self, tmp_path: Path) -> Simulation:
        wm = WorldModel(data_dir=str(tmp_path))
        causal = CausalEngine(data_dir=str(tmp_path))
        wm.add_entity(Entity(id="svc1", entity_type="service", name="auth-api",
                              properties={"version": 1, "healthy": True}))
        s = Simulation(wm, causal)
        yield s
        wm.close()
        causal.close()

    def test_simulate_action(self, sim: Simulation) -> None:
        action = Action(id="a1", description="Upgrade to v2", target_entity_id="svc1",
                        property_changes={"version": 2})
        result = sim.simulate(action)
        assert result.score > 0
        assert any("version" in e for e in result.effects)

    def test_simulate_nonexistent_entity(self, sim: Simulation) -> None:
        action = Action(id="a1", description="test", target_entity_id="ghost",
                        property_changes={"x": 1})
        result = sim.simulate(action)
        assert result.score == 0.0
        assert "not found" in result.reasoning

    def test_compare_actions(self, sim: Simulation) -> None:
        a1 = Action(id="a1", description="Small change", target_entity_id="svc1",
                     property_changes={"version": 2})
        a2 = Action(id="a2", description="Big change", target_entity_id="svc1",
                     property_changes={"version": 3, "healthy": False, "replicas": 5})
        results = sim.compare_actions([a1, a2])
        assert len(results) == 2
        # More changes should score higher
        assert results[0].action.id == "a2"

    def test_best_action(self, sim: Simulation) -> None:
        a1 = Action(id="a1", description="Small", target_entity_id="svc1",
                     property_changes={"version": 2})
        a2 = Action(id="a2", description="Big", target_entity_id="svc1",
                     property_changes={"version": 3, "healthy": False, "replicas": 5})
        best = sim.best_action([a1, a2])
        assert best is not None
        assert best.action.id == "a2"

    def test_best_action_empty(self, sim: Simulation) -> None:
        assert sim.best_action([]) is None

    def test_what_if(self, sim: Simulation) -> None:
        result = sim.what_if("svc1", {"version": 3}, "upgrade to v3")
        assert result.score > 0
        assert "upgrade" in result.reasoning
