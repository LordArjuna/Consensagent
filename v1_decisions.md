# V1 — Decisions Made So Far

A record of what's been decided in conversation. Anything not listed here is still open, and that's intentional.

---

## Project shape

- **Goal:** multi-agent system that takes a natural-language query, retrieves unstructured web data, and (eventually) produces a visualization.
- **This iteration (V1, Phase 1):** Streamlit UI + LangGraph orchestration + Planner + Retrieval + Extraction + retriever caching. Viz generation and the evaluator-optimizer loop are explicitly Phase 2.
- **Production-grade build**, no fixed time limit. Learning project.

---

## V1 query scope

You committed to handling analytical queries that map onto a dimensional model:

- **Measures**: numeric things to plot (GDP, population, energy capacity, etc.)
- **Dimensions**: ways of slicing measures (time, region)
- **Filters**: dimension values (specific countries, specific year ranges)

Locked for V1:

- **Time grain:** annual only
- **Geographic grain:** country only (no states, cities, sub-national)
- **Query shapes in scope:** single/multi measure × single/multi region, time-series and single-point comparisons

---

## Open questions (you haven't answered these yet)

These came up in conversation but you haven't pinned them down. They should be resolved before serious coding starts, because they change downstream design.

1. **Derived measures** (GDP per capita, growth rate, CAGR). You noticed GDP per capita isn't a "slice" — it's a derived measure. You haven't said how V1 handles it.

2. **Ranking queries** ("top 5 by X"). You acknowledged ordering and limiting aren't yet in your schema.

3. **Ambiguity policy.** When a query is ambiguous (e.g., "GDP growth rate" with no time period), what does the planner do — pick a default, refuse, or ask?

4. **Retrieval tier choice.** You said Tier 2 (search + extract). You haven't picked a specific provider.

5. **How decomposition is decided.** You agreed structural parsing always helps, but splitting into multiple sub-queries only helps for compositional queries. You haven't said how the planner decides when to split.

---

## Decisions made about components

### Planner
- Output is structured (not free-form). You're going to use a Pydantic-style schema, validated after the LLM call.
- Validation failures retry the LLM with the error fed back in.
- An eval set of hand-written `(query → expected output)` pairs is needed before optimizing the prompt.

You have **not** yet defined the exact fields of the planner's output object — that's still your call to make.

### Retriever
- Tier 2 (search + extract), single provider for V1, no fallback yet.
- Wrapped behind an interface so the provider is swappable.
- Caches results from day one.

### Extractor
- You leaned toward **one extractor invocation per sub-query (per leaf)**, with a separate deterministic merge step combining results. You haven't fully locked this — worth confirming.

### Cache
- Caches retrieval API responses (not LLM responses).
- You haven't decided cache implementation (disk, Redis, sqlite) or TTL.

### State schema and graph structure
- LangGraph with parallel fan-out for retrieval.
- You have **not** yet defined the state schema fields, reducer choices, or the exact node-to-node edges. This is the next big design step.

### Streamlit UI
- POC frontend, talks directly to the LangGraph pipeline in-process.
- No FastAPI in V1.

---

## What to focus on this iteration

In rough order of when each becomes blocking — not a strict build sequence, just dependency notes:

1. **Lock the open questions above.** Especially derived measures, ambiguity policy, and the decomposition-decision rule. These shape the planner's contract.
2. **Write out the planner's output object explicitly** — fields, types, what's required. Test it on paper against 8-10 example queries before any code.
3. **Define the LangGraph state schema.** Decide which data objects live in state and which don't, and which fields need reducers.
4. **Write the planner eval set** before writing the planner prompt. 15-20 queries with expected outputs.
5. Then start coding bottom-up: data objects → cache → retriever client → planner → eval-driven prompt iteration → other nodes → graph wiring → Streamlit.

---

## Things explicitly deferred to later phases

- Viz code generator
- Evaluator-optimizer loop
- Sandbox runner for generated code
- FastAPI / deployment / auth
- Observability stack (LangSmith, structured logs, metrics)
- Cost guards, prompt-injection sanitizer
- Multi-user concerns
