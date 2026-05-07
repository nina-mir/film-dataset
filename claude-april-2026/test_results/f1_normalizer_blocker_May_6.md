### Bug discovered during validation: see N-5 entry below.

# F-1 / N-5: Cross-column fuzzy permissiveness — normalizer blocker

**Status:** Open, blocking T15/T18 and any further e2e validation.
**Discovered:** May 6, 2026 during N-1 Layer 3 regression sweep.
**Pre-existing:** Yes. Would have fired with or without N-1.

---

## Summary

`fuzzy_match_cluster` searches every column of `known_values` for any cluster, with no awareness of query intent. When a cluster fails to match its intended column at the column's cutoff, the matcher continues iterating and accepts the first match in any other column at that column's cutoff. Combined with the `Locations` cutoff of 0.65 — set low because Locations values are long free-text strings — this allows person-name clusters to match unrelated Locations free-text.

## The catastrophic case

Query:      films starring alan arkin
Normalized: films starring beach and larkin
Corrections: [{'original': 'alan arkin', 'corrected': 'Beach and Larkin',
'column': 'Locations', 'source': 'fuzzy_cluster'}]

This is worse than the original Larkin street bug. The original bug was a street query hijacked by an actor match. This is an **actor query hijacked by a location match** — same failure class, opposite direction. A user asking about Alan Arkin films now gets films shot at the intersection of Beach Street and Larkin Street.

## Why this fires

Trace for `films starring alan arkin`:

1. Words after preprocessing: `['films', 'starring', 'alan', 'arkin']`.
2. `films` → DOMAIN_WORDS (skip). `starring` → DOMAIN_WORDS (skip). `alan arkin` → 2-word cluster.
3. N-1 phrase pre-pass at ≥0.95: no match (Locations has no value `alan arkin`).
4. N-1 street-context pre-pass: `alan` not in street tokens; no lock.
5. Cluster falls through to `fuzzy_match_cluster`.
6. Iterates columns. Director (cutoff 0.75): no match. Writer (0.75): no match. Actor (0.75): `alan arkin` is exact-equal to a known Actor value, **should match here** — but the matcher's column-iteration order or its acceptance criterion lets Locations win first. (Investigation needed: whether the Locations match at ratio ~0.68 is being accepted before the Actor match at ratio 1.0.)
7. Returns `Beach and Larkin` from Locations.

The fact that `alan arkin` is an exact Actor value and STILL loses to `Beach and Larkin` from Locations means there's also a column-precedence bug separate from the cutoff issue.

## Severity

**Blocker.** Any query of the form `films starring <actor>`, `films featuring <actor>`, `films directed by <director>` is at risk of being silently rewritten to a fuzzy Locations match. T15 and T18 don't trigger this directly, but the broader T1–T34 sweep almost certainly contains queries that do. Running e2e validation while this bug is live would produce contaminated results.

## What's required to unblock

Two architectural changes, separable but both needed:

1. **Context-aware column gating.** Extract intent cues from query (`starring`, `featuring`, `directed by`, `written by`, `on`, `at`, `filmed at`, etc.). Per cluster, infer which columns are eligible based on surrounding cue words. Pass `allowed_columns` to `fuzzy_match_cluster`.

2. **Column-precedence audit.** Even with gating, the fact that an exact Actor match loses to a fuzzy Locations match suggests `fuzzy_match_cluster` may not return the highest-ratio match across columns — it may return the first match it finds. Needs investigation.

Design notes for (1) under discussion separately. (2) is a code-reading task probably resolvable in an hour.

## Related items

- **C-1: Cross-street and preposition contexts** (`on larkin`, `at larkin`, `larkin and hyde`) — separate normalizer item, lower priority than F-1.
- **F-2: Locations cutoff calibration** (0.65 may be too low even with gating in place) — separate item, lower priority.
- **N-2: Short-cluster cutoff floor** (April 26 open item, originally proposed alongside N-1) — addresses single-token person fuzzy-matches like `films featuring larkin → alan arkin`. Mostly subsumed by F-1 if gating works, but worth keeping as backstop.

## Discovered alongside (not blocking but worth noting)

- `films featuring larkin` → no correction (fine: no person-cue, but also no location-cue). Bare `larkin` falls through cleanly. Behavior currently safe.
- `films on larkin` → `films on alan arkin` (BAD: location cue `on` exists, but street-context pre-pass requires explicit suffix in v1). Would be fixed by either F-1 (`on` as Locations cue) or C-1 (preposition context in street-context pre-pass). Both routes converge.