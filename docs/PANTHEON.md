# The Pantheon — ODIN's Full Subsystem Blueprint

> The maximal vision: every capability we can think of that moves ODIN toward
> **AGI-like generality** — and past today's models — mapped onto a complete Norse
> mythology. This is the *ambition*. The [`ROADMAP.md`](ROADMAP.md) sequences it into
> shippable phases.

**This document is deliberately honest.** ODIN is an *AGI-like* system, not AGI. Each
subsystem is tagged with a feasibility tier so the ambition never masquerades as a solved
problem. Where something is an open research problem, it says so.

## Feasibility legend

| Tier | Meaning |
|------|---------|
| 🟢 **Now** | Buildable with current, proven techniques — engineering, not research. |
| 🟡 **Near** | Active research; partial solutions exist; needs real R&D and evaluation. |
| 🔴 **Open** | No known robust solution. Aspirational. Pursue with humility and guardrails. |

The guiding law never changes across tiers: **intelligence lives in the loop, the verifier,
the memory, and the safety bounds — not in a bigger model.** ODIN orchestrates frontier
LLMs; it does not pretend to be a new one.

---

## Map of the Nine Realms (capability domains)

```
                              ┌─────────────────────────────┐
                              │   ASGARD — control plane     │
                              │   (secure orchestration)     │
                              └──────────────┬──────────────┘
                                             │
        ┌───────────── YGGDRASIL — world model / knowledge substrate ─────────────┐
        │                                                                          │
   ┌────┴─────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────┴──────┐
   │ COGNITION│   │   ACTION     │   │ VERIFICATION │   │   LEARNING   │   │   SAFETY    │
   │  (mind)  │   │  (hands)     │   │  (judgment)  │   │ (adaptation) │   │ (alignment) │
   └────┬─────┘   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   └──────┬──────┘
   ODIN/HUGINN/     THOR/SLEIPNIR/    LOKI/MJÖLNIR/      IDUNN/GERI&FREKI/   HEIMDALL/FENRIR/
   MUNINN/MIMIR/    GUNGNIR/VALKYRIES/ TÝR/FORSETI/      KVASIR/runes        GLEIPNIR/BALDR/
   NORNS/VÖLVA/     DRAUPNIR/         VÉ&VILI                                 GJALLARHORN/
   BRAGI/SAGA       RATATOSKR/BIFRÖST                                         RAGNARÖK/EIR
        │                                                                          │
        └────────────── RATATOSKR — message bus runs up & down ────────────────────┘
                                             │
                              ┌──────────────┴──────────────┐
                              │   MIDGARD — human + world    │
                              │   interface (users, APIs)    │
                              └─────────────────────────────┘
```

---

## I. Substrate & World Model

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **YGGDRASIL** | The world tree connecting the nine realms | The unified **world model & knowledge graph** that every subsystem reads/writes. Gives ODIN a coherent, persistent model of entities, relations, and state — the backbone of generalization. | Typed knowledge graph (Neo4j / RDF) + vector index; entities with provenance; continuously updated from MIMIR and the ravens. | 🟡 Near |
| **GINNUNGAGAP** | The primordial void before creation | The **generative latent space / simulation sandbox** — a safe "imagination" where plans and code are tried before they touch reality. | Sandboxed worktrees + simulators + LLM rollouts; nothing here has external side effects. | 🟢 Now |
| **AUDHUMLA** | The primordial cow that nourished the first beings | The **data ingestion & curation pipeline** that feeds learning — deduplicated, provenance-tagged, quality-filtered. | ETL + dedup + provenance tagging + quality/toxicity filters; feeds IDUNN. | 🟢 Now |
| **KVASIR** | The wisest being; his mead grants wisdom | **Knowledge synthesis & distillation** — fuses many sources/agents into one distilled, citable answer or compact model. | Multi-source RAG fusion; distillation of large-model behavior into cheaper specialists. | 🟢 Now |

## II. Cognition Core — the mind

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **ODIN** | The Allfather who sacrificed an eye for wisdom | **Meta-orchestrator & hierarchical planner.** Decomposes goals into Plan-DAGs, allocates agents, runs the cognitive loop, performs metacognition (reasoning about its own reasoning). | The orchestration loop (built in Phase 1) + hierarchical task networks + reflection. | 🟢 Now |
| **HUGINN** | Raven of *Thought* | **Fast, exploratory reasoning (System 1).** Hypothesis generation, brainstorming, divergent search, live web research. | Cheap-model sampling at higher temperature; tree/graph-of-thought search; web tools. | 🟢 Now |
| **MUNINN** | Raven of *Memory* | **Reflection, episodic recall & self-modeling (System 2).** Pairs with ODIN for deliberate reasoning; drives self-improvement by remembering what failed and why. | Episodic memory replay + reflection prompts; the RSIP proposer (see Phase 4). | 🟢 Now |
| **MIMIR** | The severed head at the well of wisdom | **Long-term semantic memory + retrieval.** Working / episodic / semantic / procedural stores with hybrid (dense + keyword) retrieval and provenance. | Built in Phase 1 (SQLite FTS5 + Chroma + NetworkX). Scales to Neo4j + dedicated vector DB. | 🟢 Now |
| **NORNS** (Urðr · Verðandi · Skuld) | The three who weave fate: past · present · future | **Temporal & causal reasoning.** Urðr = causal attribution over history; Verðandi = current-state estimation; Skuld = forecasting & risk under uncertainty. | Causal graphs + time-series/state estimation + probabilistic forecasting; feeds planning. | 🟡 Near |
| **VÖLVA** (Seiðr) | The seeress who foretells Ragnarök | **World-model simulation & counterfactuals.** "What-if" rollouts, Monte-Carlo planning, model-based lookahead before committing actions. | Model-based planning over YGGDRASIL; LLM-driven rollouts + tree search; calibrated value estimates. | 🟡 Near |
| **BRAGI** | God of poetry & eloquence | **Creativity & divergent generation.** Ideation, novel combination, style and register control. | Controlled sampling (diversity vs determinism), idea-recombination, critic-gated quality. | 🟢 Now |
| **SAGA** | Goddess of history & storytelling | **Narrative memory, provenance & explanation.** Every decision is a chronicle: who did what, why, with what evidence — the basis of auditability and explainability. | Append-only event log + provenance chain + natural-language explanation generation. | 🟢 Now |
| **RUNES** (Galdr) | The runes Odin won by self-sacrifice | **Interpretability & introspection.** Mechanistic insight into *why* a decision was made; surfacing internal features and attention. | Attribution methods, probing, feature/circuit analysis on open models; chain-of-thought audit. | 🔴 Open |

## III. Action & Execution — the hands

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **THOR** | God of thunder; the doer | **Executor.** Runs tools, writes/executes code, takes actions in the world. Never self-approves. | Built in Phase 1: sandboxed code interpreter, web search, tool registry. | 🟢 Now |
| **GUNGNIR** | Odin's spear that never misses its mark | **High-precision, decisive action.** Structured tool-calling and committed outputs that hit their target exactly. | Constrained/grammar-based decoding + structured function-calling + schema validation. | 🟢 Now |
| **SLEIPNIR** | Odin's eight-legged steed, fastest across realms | **Massive parallelism & adaptive compute.** Parallel DAG execution, multi-path inference, speculative decoding; spend more compute on hard nodes. | Async DAG scheduler + speculative decoding + difficulty-routed compute. | 🟢 Now |
| **VALKYRIES** | Choosers of the slain | **Routing, scheduling & model selection.** Decide which agent/model/tool handles each task (cheap vs frontier), and which jobs get resources. | Cost/quality router + priority scheduler + MoE-style expert selection. | 🟢 Now |
| **DRAUPNIR** | Odin's ring that drips eight new rings every ninth night | **Self-replication & autoscaling.** Spawns specialized sub-agents and scales horizontally on demand, then reclaims them. | Dynamic agent spawning + serverless autoscaling + lifecycle/budget caps. | 🟢 Now |
| **RATATOSKR** | The squirrel carrying messages up & down Yggdrasil | **Inter-agent message bus / event routing.** The nervous system connecting all subsystems. | Event-driven pub/sub + durable queues; typed `AgentMessage` envelopes. | 🟢 Now |
| **BIFRÖST** | The rainbow bridge to the outside world | **The bridge to reality** — GitHub, deployment, external APIs, and (later) embodiment endpoints. All egress is gated by HEIMDALL. | Atomic git engine (branch → commit → push → PR), API connectors, least-privilege tokens. | 🟢 Now |

## IV. Verification, Truth & Judgment

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **LOKI** | The trickster who tests the gods | **Adversarial critic / red-team.** Decorrelated review (different model family) to catch what the proposer missed. | Built in Phase 1; adversarial prompts + structured verdicts. | 🟢 Now |
| **MJÖLNIR** | Thor's hammer — forged true | **Formal verification & guarantees.** Proofs, property-based tests, type/contract checks for code, infra, and plans. Turns "probably right" into "provably within spec." | Property-based testing, type checking, SMT/formal methods for critical paths. | 🟡 Near |
| **TÝR** | God of law who sacrificed his hand to bind Fenrir | **Contracts, oaths & guarantees.** SLAs, commitments, and the permission agreements that bound powerful actions — willing to pay a cost for safety. | Contract schemas + commitment tracking + policy-as-code. | 🟢 Now |
| **FORSETI** | God of reconciliation & justice | **Multi-agent consensus & debate adjudication.** Resolves disagreements between agents; runs structured debate and judges the winner. | Debate protocols + voting/consensus + judge model with rationale. | 🟡 Near |
| **VÉ & VILI** | Odin's brothers, co-creators | **Ensemble cognition.** Multiple independent reasoners whose decorrelated errors cancel — diversity as reliability. | N-way sampling across model families + aggregation/selection. | 🟢 Now |

## V. Learning & Adaptation

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **IDUNN** | Keeper of the apples of youth | **Continual learning & knowledge freshness.** Keeps ODIN from going stale without full retrains; mitigates catastrophic forgetting. | Parameter-efficient updates (LoRA/adapters) on curated fresh data + retrieval-first freshness via MIMIR. | 🟡 Near |
| **GERI & FREKI** | Odin's ever-hungry wolves | **Active learning & curiosity.** Intrinsic drive to seek the data/experiences that most reduce uncertainty. | Uncertainty-driven data acquisition + curiosity rewards + targeted exploration. | 🟡 Near |
| **VÍGRÍÐR** | The field foretold for the last battle | **The proving ground.** A held-out **benchmark arena** every self-improvement candidate must survive before it ships. *This is what stops self-improvement from becoming self-degradation.* | Fixed eval suite with known-good outcomes; accept a change only if it keeps all tests green **and** improves a target metric without regression. | 🟢 Now |

## VI. Self-Improvement & Metacognition (RSIP)

ODIN's most distinctive capability: it improves **its own code, prompts, and skills** —
**bounded, verified, and human-gated.** Driven by MUNINN (reflection) and proven on VÍGRÍÐR.

```
MUNINN observes a weakness  →  proposes a SCOPED change on an ISOLATED branch (never main)
   →  VÍGRÍÐR: full tests + benchmark eval in GINNUNGAGAP (sandbox)
   →  LOKI adversarial review of the diff  →  HEIMDALL caps (scope/risk/budget)
   →  BIFRÖST opens a PR  →  CI  →  HUMAN approves merge  →  reload (always git-revertible)
```

- **Non-negotiable:** HEIMDALL (the safety layer) and VÍGRÍÐR (the eval) are the two things
  ODIN **cannot silently rewrite**. Self-improvement that can weaken its own brakes or its own
  exam is not self-improvement — it's decay. 🟢 **Now** (the loop) / 🔴 **Open** (unbounded,
  fully-autonomous self-rewrite — intentionally *not* a goal).

## VII. Perception & Multimodality

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **HEIMDALL's senses** | He sees to the ends of the world and hears grass grow | **Multimodal perception & monitoring.** Vision, audio, structured data; plus always-on telemetry sensing. | Multimodal provider APIs (image/audio/table) + streaming telemetry. | 🟢 Now |
| **VEÐRFÖLNIR** | The hawk perched atop Yggdrasil's eagle | **High-level scene/situation understanding.** Abstracts raw perception into entities and affordances for the world model. | Vision-language models feeding YGGDRASIL entities. | 🟡 Near |
| **JÖRMUNGANDR** | The serpent encircling Midgard | **Embodiment / environment boundary.** Actuation in digital or physical environments and the network perimeter around them. | Robotics/RPA actuators + sandboxed environment APIs (optional, far-future for physical). | 🔴 Open |

## VIII. Social & Emotional Intelligence

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **FREYA** | Goddess of love | **Empathy, theory-of-mind & communication.** Models user intent/affect; tailors tone; renders the final cited answer humanely. | Affect/intent recognition + tone control via SFT; *recognize, never manipulate*. | 🟢 Now |
| **FRIGG** | Queen who knows all fates but stays silent | **Privacy & discretion.** Knows much, reveals only what's appropriate — confidentiality, PII handling, need-to-know. | PII detection/redaction + access control + data-minimization policy. | 🟢 Now |

## IX. Safety, Alignment & Containment

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **HEIMDALL** | The ever-watchful guardian of Bifröst | **The safety gate & monitor.** Capability matrix, approval gates, budget, injection defense, anomaly detection. All egress passes through it. | Built in Phase 1; extended with ML anomaly detection. | 🟢 Now |
| **GJALLARHORN** | The horn Heimdall blows to warn of Ragnarök | **Alerting & escalation.** Sounds the alarm — incident response, human escalation, automatic pause. | Alerting + on-call escalation + auto-halt hooks. | 🟢 Now |
| **HLIDSKJALF** | Odin's high seat, from which he sees all realms | **Global observability.** Live view of plans, verdicts, budgets, memory, and self-improvement history. | Dashboards + distributed tracing + metrics over SAGA's log. | 🟢 Now |
| **FENRIR** | The monstrous wolf that must stay bound | **Capability containment.** The most powerful/dangerous tools kept sandboxed and leashed. | Strong sandboxing (containers/VMs), egress filtering, capability tokens. | 🟢 Now |
| **GLEIPNIR** | The deceptively-soft, unbreakable fetter binding Fenrir | **The guardrails themselves** — hard, tamper-evident constraints that hold even powerful capabilities. | Policy-as-code + immutable limits + tamper-evident audit; constraints ODIN can't self-edit. | 🟡 Near |
| **BALDR** | The beloved, pure god whose death triggers Ragnarök | **The alignment & values core.** The objectives/values ODIN protects. "Guarding Baldr" = keeping the system aligned and corrigible. | Constitutional rules + preference models + corrigibility (accepts correction/shutdown). | 🔴 Open |
| **VÁR** | Goddess of oaths and agreements | **Consent & permissioning.** Explicit agreements for sensitive actions; revocable scopes. | Consent prompts + scoped, revocable permissions + audit. | 🟢 Now |

## X. Resilience, Economy & Efficiency

| Subsystem | Myth | Role / AGI contribution | How it's built | Tier |
|-----------|------|-------------------------|----------------|------|
| **EIR** | Goddess of healing | **Self-repair & fault tolerance.** Detects failures, retries, heals, and rolls back to last-good state. | Health checks + circuit breakers + automatic rollback (every change revertible). | 🟢 Now |
| **RAGNARÖK** | The foretold catastrophe and renewal | **Disaster planning & chaos engineering.** Worst-case simulation, graceful degradation, and the global **kill-switch**. | Chaos testing + failover + degraded-mode + one-command halt. | 🟢 Now |
| **NIDHOGG** | The dragon gnawing Yggdrasil's roots | **Continuous adversarial stress.** Always-on fuzzing, red-teaming, and chaos eating at the system to find weakness first. | Fuzzers + adversarial suites + scheduled chaos runs. | 🟢 Now |
| **BROKKR & SINDRI** | The dwarven smiths who forged the gods' treasures | **The forge — build & CI/CD.** Compiles, tests, and ships the system's own tools and artifacts. | GitHub Actions CI + artifact build + reproducible packaging. | 🟢 Now |
| **SKÍÐBLAÐNIR** | The ship that always has fair wind and folds into a pocket | **Efficiency & portable deployment.** Folds small (quantization/compression), unfolds large (scale-out). | Quantization (INT4/8/FP8) + MoE sparsity + KV-cache compression + edge packaging. | 🟢 Now |
| **ANDVARI's gold** | The dwarf's hoard | **Resource economy.** A real budget economy over tokens/compute; route spend to value. | Hard budgets (built in Phase 1) + cost accounting + value-based allocation. | 🟢 Now |
| **ASGARD** | Home of the gods | **The control plane.** Secure runtime/orchestration enclave where the cognition core lives. | Hardened service runtime + secrets management + isolation. | 🟢 Now |
| **MIDGARD** | The human world | **The user & environment interface.** Where ODIN meets people and external systems. | APIs/UI + integration connectors. | 🟢 Now |

---

## How ODIN is meant to exceed today's models ("even better than you")

| Capability | A standalone LLM today (e.g. me) | ODIN's target |
|------------|----------------------------------|---------------|
| **Memory** | Stateless between sessions | Persistent lifelong memory (MIMIR + YGGDRASIL) |
| **Learning** | Frozen at training cutoff | Continual updates + retrieval freshness (IDUNN) |
| **Reliability** | Confident hallucination possible | Decorrelated verification + formal checks (LOKI, MJÖLNIR, VÉ&VILI) |
| **Reasoning depth** | Fixed compute per token | Adaptive compute + simulation/lookahead (SLEIPNIR, VÖLVA) |
| **Self-knowledge** | No introspection of errors | Reflection + self-improvement (MUNINN, VÍGRÍÐR) |
| **Agency** | Single response | Long-horizon planning + tool action + parallel agents (ODIN, THOR, DRAUPNIR) |
| **Uncertainty** | Often uncalibrated | Calibrated confidence + abstention |
| **Safety** | Guardrails at one layer | Defense-in-depth, containment, kill-switch (HEIMDALL→RAGNARÖK) |
| **Auditability** | Opaque | Full provenance + explanation (SAGA) |

These are **targets**, not claims. Several depend on the open problems below.

## What ODIN is NOT — the honest part

ODIN, even fully built, is **not AGI** and this plan does not claim it will be. The following
are genuine **open research problems** (🔴) — we design *toward* them with humility, not around
them:

- **True continual learning** without catastrophic forgetting at scale.
- **Robust value alignment & corrigibility** (BALDR) — keeping goals stable and accepting
  correction/shutdown as capability grows.
- **Mechanistic interpretability** (RUNES) — actually knowing *why* a model decided something.
- **General causal & world-model reasoning** (NORNS, VÖLVA) beyond narrow domains.
- **Physical embodiment** (JÖRMUNGANDR) — far-future and out of scope for the core system.
- **Open-ended autonomous self-rewrite** — intentionally **rejected**: self-improvement stays
  bounded, eval-gated, and human-approved. The brakes (HEIMDALL) and the exam (VÍGRÍÐR) are
  off-limits to the system itself.

The discipline that makes ODIN powerful is the same discipline that keeps it safe: typed
contracts, an independent verifier, hard budgets, defense-in-depth, and a human at the gate
for anything irreversible.
