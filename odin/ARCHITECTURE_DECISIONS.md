# Architecture Decisions — ODIN Phase 1

Deviations from the spec and rationale.

## 1. ChromaDB initialization uses `Client` not `PersistentClient`

The spec implies a persistent ChromaDB instance. ChromaDB 0.5+ changed the API —
`PersistentClient` was replaced with `Client(Settings(is_persistent=True))`. Using
the Settings-based approach for compatibility with the installed version.

## 2. No `from __future__ import annotations` guarding on StrEnum

The spec targets Python 3.11+. We use `StrEnum` directly (available since 3.11)
instead of `(str, Enum)` which ruff flags as deprecated in UP042.

## 3. Injection detection is regex-based, not ML-based

The spec says "prompt-injection defense baked in from day one." Phase 1 uses 10
hardcoded regex patterns. This catches common injection templates but is evadable
by adversarial inputs. An ML-based classifier would be more robust but introduces
a dependency and latency cost. Documented as "mitigated, not solved" in README.

## 4. Budget tracking wraps every LLM call (Phase 2 — resolved)

*Phase 1:* the provider-agnostic adapter didn't know about Heimdall, so token
budgets relied on wall-clock approximation.

*Phase 2:* the orchestrator now wraps its adapter in `TrackedLLM`
(`odin/routing/llm_adapter.py`), which forwards `resp.tokens_used` to
`BudgetState.record_llm_call()` and raises `BudgetExhausted` the moment a token
or call cap is hit. All agents (planner, executor, critic, renderer, verifier)
share the tracked adapter, so every reasoning call counts against the budget.
Known remaining gap: MIMIR's embedding calls are not yet metered.

## 5. MIMIR uses SQLite FTS5 instead of a dedicated search engine

FTS5 is built into SQLite and provides reasonable keyword search without adding
Elasticsearch or similar as a dependency. The hybrid retrieval (FTS5 + Chroma dense)
gives acceptable recall for Phase 1. A dedicated search backend can be swapped in
later via the MIMIR interface.

## 6. Semantic graph uses NetworkX with JSON serialization

The spec mentions Neo4j as a future backend. Phase 1 uses NetworkX with
`node_link_data`/`node_link_graph` JSON serialization. This is adequate for
single-process use but won't scale to concurrent access or large graphs.
The `_SemanticGraph` class is an internal abstraction that can be replaced.

## 7. Tool sandbox uses `preexec_fn` resource limits (Linux only)

The code interpreter sandbox uses `resource.setrlimit` in a `preexec_fn`. This
works on Linux but not Windows. The spec doesn't require Windows support. If needed,
a container-based sandbox would be the proper Phase 2 approach.

## 8. Skill model is stored but not auto-invoked

The spec describes procedural memory with auto-skill extraction (Phase 3). Phase 1
defines the `Skill` pydantic model and stores it, but doesn't implement automatic
skill retrieval or invocation. The interface is there; the logic is deferred.

## 9. Model router defaults to Claude Haiku/Sonnet

The spec says "cheap vs frontier" routing. We default to `claude-haiku-4-20250414`
(cheap) and `claude-sonnet-4-20250514` (frontier). These are configurable. The router
is a thin wrapper; no sophisticated cost/quality heuristics yet.

## 10. Self-consistency uses structured output + semantic similarity (Phase 2 — resolved)

*Phase 1:* the check asked the LLM to re-derive an answer, then asked the LLM
*again* to judge whether the two answers agreed — so the comparison itself could
be wrong.

*Phase 2:* the re-derivation now returns a structured `{"final_answer": ...}`
and agreement is decided **deterministically** by `SemanticComparator`
(`odin/verify/similarity.py`) — token cosine + containment by default, or an
injected embedding function for true semantic similarity. This removes the
second fallible LLM judge call (and saves a call per verification). The lexical
default can still be fooled by near-synonyms; inject embeddings for stronger
semantics.

## 11. FREYA is a single-pass renderer

The spec describes FREYA as a presentation agent. Phase 1 implements a single LLM
call that formats results with citations. No iterative refinement or template system.
The interface supports adding these in Phase 2.
