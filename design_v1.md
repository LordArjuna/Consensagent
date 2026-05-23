# Data Viz Multi-Agent System — V1 Design Doc

**Status:** Draft for POC / V1 Phase 1
**Scope:** Streamlit UI + LangGraph orchestration + Planner + Retrieval/Extraction + Retriever caching
**Out of scope (deferred):** Viz generator, evaluator-optimizer loop, sandbox runner, deployment, observability stack, cost guards, auth, multi-user concerns

---

## 1. Goals & Non-Goals

### Goals
- End-to-end working pipeline: user query → planner → retrieval → extraction → structured dataset (no viz yet in this phase, but data is ready for it).
- Local-only execution; Streamlit app talks to LangGraph directly.
- Constrained query shape so every component has a tight contract.
- Cached retrieval so iterating on prompts is cheap.

### Non-Goals (V1 Phase 1)
- No production deployment, no auth, no multi-user state.
- No viz generation or evaluator-optimizer loop (Phase 2).
- No re-planning, no human-in-the-loop clarification (deferred).
- No fallback search providers (single provider, fail loud).
- No derived measures, no sub-national geography (see V1 Scope below).

---

## 2. V1 Scope (the contract with ourselves)

**V1 handles:**
- Atomic numeric measures (GDP, population, energy capacity, etc.) — no derived/computed measures.
- Dimensions: `time` (annual grain only) and `region` (country grain only).
- Query shapes:
  - Single-measure, single-region, time series ("India GDP over 10 years").
  - Multi-measure, multi-region time series ("India and China GDP and population over 10 years").
  - Single-time-point comparisons ("India GDP in 2014 vs 2024") — *if straightforward to support; otherwise deferred*.
- Up to N measures × M regions (bound below) per query.

**V1 explicitly does NOT handle:**
- Derived measures (GDP per capita, growth rate, CAGR). **OPEN QUESTION — see §11.**
- Sub-national geography (states, cities).
- Sub-annual grains (monthly, quarterly).
- Ranking queries ("top 5 countries by GDP"). **OPEN QUESTION — see §11.**
- Ambiguous queries — V1 takes a fixed default and surfaces the assumption. **OPEN QUESTION — see §11.**

**Bounds (chosen now, tune later):**
- Max measures per query: 4
- Max regions per query: 4
- Max sub-queries after planning: 16 (= 4 × 4 worst case)
- Max retrieval results per sub-query: 5
- Planner retry on validation failure: 2

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ Streamlit UI                                             │
│   - Query input                                          │
│   - Progress display (per-node status)                   │
│   - Final structured data preview (table)                │
│   - Execution trace expander                             │
└────────────────────┬─────────────────────────────────────┘
                     │ direct in-process call
                     ▼
┌──────────────────────────────────────────────────────────┐
│ LangGraph StateGraph                                     │
│                                                          │
│   START → planner → [fan-out via Send] → retriever (×N)  │
│                            │                             │
│                       [reducer join]                     │
│                            ▼                             │
│                       extractor (×N, one per sub-query)  │
│                            │                             │
│                       [reducer join]                     │
│                            ▼                             │
│                         merger → END                     │
│                                                          │
│   Checkpointer: in-memory (V1) → Postgres (later)        │
└────────────────────┬─────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   ┌────────┐  ┌─────────┐  ┌──────────┐
   │ LLM    │  │ Retriev │  │ Cache    │
   │ client │  │ API     │  │ (disk    │
   │        │  │ (Tier 2)│  │  JSON)   │
   └────────┘  └─────────┘  └──────────┘
```

Linear-with-fan-out shape. No conditional edges in this phase. We add the evaluator retry edge in Phase 2.

---

## 4. Data Objects

All defined as Pydantic models. These are the wire-level contracts between nodes; LangGraph state holds references to them.

### 4.1 `UserRequest`
- `conversation_id: str`
- `query: str` — raw user text

### 4.2 `Measure`
- `name: str` — e.g., "GDP", "population"
- `unit: str | None` — e.g., "USD", "people"; planner may leave None if unspecified

### 4.3 `RegionFilter`
- `countries: list[str]` — ISO names or common names; normalization deferred

### 4.4 `TimeFilter`
- `start_year: int`
- `end_year: int`
- *Note: if user says "last 10 years," planner resolves against current year.*

### 4.5 `PlannerOutput`
- `measures: list[Measure]` (length 1..4)
- `region_filter: RegionFilter` (1..4 countries)
- `time_filter: TimeFilter`
- `assumptions: list[str]` — natural-language strings the planner had to assume (e.g., "assumed annual grain", "assumed real USD"). Surfaced to user.
- `sub_queries: list[SubQuery]` — derived Cartesian product, see below

### 4.6 `SubQuery`
- `id: str` — stable hash of (measure, country); used for joining results back
- `measure: Measure`
- `country: str`
- `time_filter: TimeFilter` — copied from parent
- `search_string: str` — the actual query string sent to the retrieval API

### 4.7 `RetrievalResult`
- `sub_query_id: str` — links back to the SubQuery
- `url: str`
- `title: str`
- `cleaned_text: str` — from Tier-2 API's extract mode
- `fetched_at: datetime`
- `source_score: float | None` — provider-supplied relevance, if any

### 4.8 `DataPoint`
- `year: int`
- `value: float`
- `unit: str | None`
- `source_url: str` — provenance
- `confidence: Literal["high", "medium", "low"]`

### 4.9 `Series`
- `sub_query_id: str`
- `measure: Measure`
- `country: str`
- `points: list[DataPoint]` — sorted by year
- `extraction_notes: str | None` — anything the extractor flagged (gaps, conflicting sources, etc.)

### 4.10 `MergedDataset`
- `query: str` — original
- `assumptions: list[str]` — surfaced to user
- `series: list[Series]` — one per (measure × country)
- `time_range: TimeFilter`
- *This is the V1 final output. Phase 2 hands this to the viz generator.*

---

## 5. LangGraph State Schema

State is what flows through the graph. Note: **not every data object lives in state.** State holds what nodes need to read/write; ephemeral data (raw HTML before cleaning) does not.

```python
class GraphState(TypedDict):
    # Input
    user_request: UserRequest

    # Planner output
    planner_output: PlannerOutput | None

    # Fan-out scratch space (parallel writes — need reducers)
    retrieval_results: Annotated[list[RetrievalResult], operator.add]
    series: Annotated[list[Series], operator.add]

    # Final
    merged_dataset: MergedDataset | None

    # Control / observability
    errors: Annotated[list[NodeError], operator.add]
    node_log: Annotated[list[NodeLogEntry], operator.add]
```

**Reducer notes:**
- `retrieval_results` and `series` use `operator.add` because parallel retriever/extractor branches each append.
- `errors` and `node_log` are append-only audit trails — every node writes one entry, regardless of success.
- `merged_dataset` is written once by the merger node — no reducer needed.

**State hygiene rules:**
- No node mutates fields written by another node (except via reducer).
- `retrieval_results` and `series` are truncated after the merger runs (keep state small for checkpointing).
- Raw HTML and full search-engine responses are **not** stored in state — only the cleaned `RetrievalResult` is.

---

## 6. Graph Structure

```
nodes:
  - planner
  - retriever       (invoked via Send, one per SubQuery)
  - extractor       (invoked via Send, one per sub_query_id)
  - merger

edges:
  START          → planner
  planner        → [Send(retriever, sq) for sq in planner_output.sub_queries]
  retriever      → [Send(extractor, sq_id) for sq_id in unique sub_query_ids]
  extractor      → merger
  merger         → END
```

**Why two fan-outs:**
- Retriever fan-out: one parallel call per `SubQuery` (the API call).
- Extractor fan-out: one parallel LLM call per `sub_query_id`, grouped from the retrieval results for that sub-query. The extractor sees only the 5 results for *its* sub-query, not all 20+ — much tighter prompt, much better extraction quality.

**Checkpointer:** `MemorySaver` for V1. Will swap to `PostgresSaver` in production. The interface doesn't change; the checkpointer is injected at compile time.

**Per-node timeouts (initial values):**
- planner: 30s
- retriever: 60s (network)
- extractor: 60s
- merger: 5s (deterministic, no LLM)

**Retry policy:** none in V1. If a node fails, the error is logged and the graph proceeds with whatever it has. Empty `RetrievalResult` lists just produce empty `Series`. The merger handles the empty case.

---

## 7. Planner

### 7.1 Responsibilities
1. Parse `query` into structured `measures`, `region_filter`, `time_filter`.
2. Identify and surface assumptions (default time range, default unit, etc.).
3. Validate the parsed structure against bounds.
4. Generate `SubQuery` list as the Cartesian product of measures × countries.

### 7.2 Implementation
- Single LLM call with **structured output** (Pydantic schema enforced).
- Model: capable tier (Claude Sonnet / GPT-4-class) — planner is low-volume, high-leverage.
- Prompt template includes:
  - The schema (so the LLM knows the field shape).
  - Few-shot examples covering: single measure single region, multi measure multi region, ambiguous query.
  - The bounds (max 4 measures, max 4 regions) as hard constraints.
  - Explicit instruction: "If query is out of V1 scope, set `out_of_scope: true` with reason."

### 7.3 Validation (post-LLM, in Python)
- Bounds check (≤4 measures, ≤4 regions).
- Time range sanity (start ≤ end, end ≤ current year, start ≥ 1900).
- Non-empty measures and regions.
- Sub-queries match the Cartesian product.

If validation fails: retry the LLM up to 2 times with the validation error included in the prompt. If still failing, write to `errors` and produce an empty `PlannerOutput` — graph still runs to END cleanly.

### 7.4 Search-string synthesis
Each `SubQuery.search_string` is built deterministically (no LLM): `f"{measure.name} of {country} {time_filter.start_year}-{time_filter.end_year}"`. Templated, easy to swap.

*Rationale: keeping the search-string generation deterministic means we can A/B different templates later without re-running the planner LLM call.*

### 7.5 Planner eval set
At least 20 hand-written `(query, expected_PlannerOutput)` pairs. Run on every prompt change. Metrics:
- Exact match on measure names (after normalization).
- Exact match on country list.
- Time range within ±1 year tolerance.
- Sub-query count matches.

---

## 8. Retrieval & Extraction

### 8.1 Provider choice (V1)
**Tier 2: search + extract API.** Specific provider TBD between Tavily, Exa, and Firecrawl. Decision criteria:
- Free tier sufficient for development (≥500 calls/month).
- Returns cleaned page text, not just URLs.
- Has a Python SDK.
- Reasonable rate limits.

**Wrapped in a thin `RetrieverClient` interface.** Concrete provider is swappable; no node imports the provider SDK directly.

### 8.2 Retriever node
- Input: one `SubQuery`.
- Calls `RetrieverClient.search_and_extract(search_string, max_results=5)`.
- Output: list of `RetrievalResult` appended to state.
- Filters in this phase: drop results below a length threshold (e.g., < 200 chars cleaned text — likely junk).
- No relevance re-ranking in V1.

### 8.3 Extractor node
- Input: all `RetrievalResult`s with a given `sub_query_id`, plus the corresponding `SubQuery` (so the extractor knows what measure/country/time to extract).
- LLM call with structured output → `Series`.
- Model: cheaper tier (Haiku / GPT-4-mini) — extraction is the high-volume LLM workload.
- Prompt template:
  - Schema for `Series` and `DataPoint`.
  - The `SubQuery` (so the LLM knows the target).
  - The cleaned text from all results, **delimited and labeled with source URLs**.
  - Instructions:
    - Extract only data matching the requested measure, country, and time range.
    - Cite the source URL for each `DataPoint`.
    - Flag conflicting values across sources in `extraction_notes` (don't silently pick).
    - Mark confidence `low` if only one source, `medium` if 2+ agree, `high` if 3+ agree.
    - Return empty `points` list rather than hallucinating.

### 8.4 Prompt injection note
Retrieved web text is **untrusted input**. The extractor prompt must:
- Clearly delimit retrieved content (XML tags or fenced blocks).
- Include an explicit instruction that retrieved text is data, not instructions.
- Never `eval` or otherwise execute content from retrieved text.

Full sanitizer pass deferred. Acceptable risk for V1 POC.

### 8.5 Merger node (deterministic, no LLM)
- Reads all `Series` from state.
- Aligns on `(measure, country)` — there should be exactly one `Series` per pair after extraction.
- Constructs `MergedDataset`.
- If any `Series` is empty or missing, records this in `assumptions` ("no data found for X in Y") and continues.
- Writes `merged_dataset` to state.

---

## 9. Caching

### 9.1 What to cache
- **Retrieval API responses**, keyed on `search_string`.
- *Not* caching LLM calls in V1 — too easy to get stale; revisit later with prompt-versioned keys.

### 9.2 Implementation
- Disk cache: a single directory of JSON files. Filename = SHA256 of `search_string`.
- File contents: `{search_string, fetched_at, results: [RetrievalResult JSON]}`.
- TTL: 7 days (web data changes, but slowly for historical queries; tune later).
- On cache miss: call API, write file, return.
- On cache hit within TTL: read file, return.

### 9.3 Cache controls in UI
Streamlit sidebar:
- "Bypass cache" checkbox (always re-fetch).
- "Clear cache" button (delete all cache files).

### 9.4 Why this is enough for V1
- Single user, no concurrency concerns.
- Filesystem is fast enough for <1000 entries.
- Easy to inspect (just open the JSON files when debugging).
- Trivial to swap for Redis later — `RetrieverClient` is the only thing that touches the cache.

---

## 10. Streamlit UI

### 10.1 Layout
- **Sidebar:** cache controls (§9.3), provider selector (if multiple wired), model selector (planner / extractor).
- **Main:**
  - Text input for the query.
  - "Run" button.
  - Live progress: which node is currently active, with a spinner and a brief status line.
  - On completion:
    - Assumptions panel (the planner's stated assumptions).
    - Data preview: `MergedDataset` rendered as a pivoted table (rows = years, columns = country×measure).
    - Expandable "Execution trace": full `node_log` and `errors` from state.
    - "View raw state" debug expander (JSON dump).

### 10.2 How Streamlit talks to LangGraph
- Direct in-process: import the compiled graph, call `graph.stream(initial_state)`.
- Stream node-completion events to update progress in real time.
- No FastAPI in V1. Add later when we want multi-user or remote access.

### 10.3 What the UI does NOT do (yet)
- No chart rendering (Phase 2).
- No history of past queries (could store in session_state later).
- No login / multi-user.

---

## 11. Open Questions (must answer before coding)

1. **Derived measures** — pick one:
   - (a) Out of scope for V1 — planner returns `out_of_scope` for "GDP per capita".
   - (b) Pre-fetch — treat "GDP per capita" as an atomic measure, let retrieval find it pre-computed.
   - (c) Compute — planner emits `{derived: "GDP/Population", inputs: [...]}`; merger does math.
   - **Recommendation:** (a) for V1, (b) for V1.1, (c) only if needed.

2. **Ranking queries** ("top 5 by X"):
   - (a) Out of scope for V1.
   - (b) Add `order_by` and `limit` to `PlannerOutput`.
   - **Recommendation:** (a). Adds a new query shape — defer.

3. **Ambiguity policy:**
   - (a) Default-with-assumption (planner picks, surfaces in `assumptions`).
   - (b) Refuse and ask for clarification.
   - **Recommendation:** (a) for V1. (b) requires human-in-the-loop in the graph.

4. **Retrieval provider:** Tavily vs Exa vs Firecrawl — quick spike to pick one, but interface is provider-agnostic so it's swappable.

5. **LLM provider/SDK abstraction:** wrap from day 1, or hard-code Anthropic/OpenAI for V1 and refactor later? **Recommendation:** thin wrapper from day 1 — adds minimal cost, big payoff in Phase 2 when we want to A/B models.

6. **Planner failure mode:** when planner can't parse query, do we (a) return empty `PlannerOutput` and let graph reach END with nothing, or (b) raise an exception that the UI catches? Affects how errors surface.

---

## 12. Repo Layout (proposed)

```
proj/
├── app/
│   └── streamlit_app.py          # UI entry point
├── core/
│   ├── state.py                  # GraphState TypedDict, reducers
│   ├── models.py                 # All Pydantic data objects
│   ├── graph.py                  # build_graph() — wires nodes
│   ├── nodes/
│   │   ├── planner.py
│   │   ├── retriever.py
│   │   ├── extractor.py
│   │   └── merger.py
│   ├── clients/
│   │   ├── llm.py                # LLM wrapper
│   │   └── retriever.py          # RetrieverClient (Tier-2 wrapper)
│   ├── cache/
│   │   └── disk_cache.py
│   └── prompts/
│       ├── planner.txt
│       └── extractor.txt
├── evals/
│   ├── planner_set.json          # golden queries → expected PlannerOutput
│   ├── run_planner_eval.py
│   └── README.md
├── tests/
│   ├── test_models.py
│   ├── test_planner_validation.py
│   ├── test_cache.py
│   └── test_merger.py
├── pyproject.toml
└── README.md
```

---

## 13. Build Order (recommended)

Strictly bottom-up so each layer is testable before the next:

1. `core/models.py` — all Pydantic objects. Write tests asserting they serialize/deserialize.
2. `core/cache/disk_cache.py` + tests.
3. `core/clients/llm.py` — minimal LLM wrapper, one provider.
4. `core/clients/retriever.py` — wraps the Tier-2 API, uses the cache.
5. `core/nodes/planner.py` + `evals/planner_set.json` + `run_planner_eval.py`. **Stop and run the eval before moving on.** Iterate prompt until passing.
6. `core/nodes/retriever.py` — thin node wrapping `RetrieverClient`.
7. `core/nodes/extractor.py` + a small extractor eval set (5-10 cases).
8. `core/nodes/merger.py` + tests (deterministic, easy to test).
9. `core/graph.py` — wire nodes with `Send` fan-outs.
10. `app/streamlit_app.py` — UI.
11. End-to-end smoke test on 3 queries.

Things to actively resist: building the UI first, building the graph before nodes work in isolation, skipping the planner eval set.

---

## 14. What This Doc Doesn't Cover (and where it'll get covered)

- Viz generation, evaluator-optimizer loop, sandbox — Phase 2 design doc.
- Postgres checkpointer, FastAPI, deployment — Phase 3 design doc.
- Observability (LangSmith, structured logs, metrics) — Phase 3.
- Cost guards, prompt injection sanitizer, secrets — Phase 3.
- Multi-user, auth, rate limiting — Phase 3+.

Each phase gets its own doc. This one stays focused.
