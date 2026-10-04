<!-- SUMMARIZE_PROMPT_VERSION: v1 -->
# think.context.summarize — summary prompt (ADR-0283 C5)

> **v1 status: CONTRACT ONLY.** The v1 node (`summarize.py`) is an
> extractive-deterministic implementation so the acceptance bar — 100%
> retention of planted facts on fixtures — is enforceable without an LLM
> in the loop. This file is the contract a future LLM-backed summarizer
> must satisfy: same input shape, same `CompactSummary` JSON out, same
> honesty rules. `SUMMARIZE_PROMPT_VERSION` in `summarize.py` must match
> the marker above; drift is a test failure (T4).

## Input

The working-context payload region about to be discarded (ordered oldest
first). Items may be strings, dicts, or opaque objects.

## Output

A single `CompactSummary` JSON object:

```json
{
  "decisions": ["<decision statements preserved>"],
  "commitments": ["<commitments / TODOs preserved>"],
  "entity_states": ["<entity-state facts preserved>"],
  "open_questions": ["<unresolved items preserved>"],
  "dropped": ["<truncated reprs of discarded items that yielded nothing>"],
  "prompt_version": "v1"
}
```

## Rules

1. **Sediment first, always.** Every item that yields a fact in one of the
   four lists must already have been persisted through the memory write
   path (`metadata.source = "compaction"`) before this summary is built.
   The summary is a *second* copy, not the only copy.
2. **Honest `dropped`.** Any discarded item that produced no fact goes
   into `dropped` as a truncated repr (≤120 chars, at most 20 entries).
   Never silently omit a discarded item and never invent facts.
3. **No new facts.** The four lists contain only statements present in
   the input region. Paraphrase is allowed; invention is not.
4. **Determinism.** Same input region → same summary. No sampling, no
   temperature.
