# Open Items that need to be explored without any ordering 

### As a consequence of dataset_swap_2026
- It is worth flagging that "films in district 5" is a query shape that's now possible and currently unhandled. Track it in your open-items doc if it isn't already.

> The same thing applies to Neiughrborhoods, Production_company and Distributor!!

- Neighborhood match semantics (== vs contains) — defer until Phase E. Decision depends on whether the normalizer reliably canonicalizes neighborhood names from user queries; if yes, exact is cleaner given SFgov's closed ~40-value vocabulary; if normalization is unreliable, contains is more forgiving. Test cluster extractor behavior on "north beach", "russian hill", "pacific heights", "castro upper market" before deciding.

- Update phase_3_open_items_April_26.md — note that N-2's 5-char length threshold is too low (Larkin = 6 chars), add Larkin as a documented case