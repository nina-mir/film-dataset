# Dataset Swap — April 2026

> Addendum section added on April 29, 2026

**Date:** April 26, 2026
**Action:** Replaced the project's primary film-locations dataset with the updated SF Open Data release.

---

## What changed

| | Old | New |
|---|---|---|
| File | `sf_film_May7_2025_data.gpkg` | `Film_Locations_in_San_Francisco_20260424.csv` |
| Source | SF Open Data, May 7 2025 export | SF Open Data, April 24 2026 export |
| Rows | 2,084 | 2,214 |
| Geocoder | HERE API (project-side, last year) | SFgov-side (Dec 17 2024 update) |
| Geometry columns | `geometry` (built from HERE-resolved lat/lon) | `Point`, `Longitude`, `Latitude` |
| New attribute columns | — | `Analysis Neighborhood`, `Supervisor District` |
| Other new columns | — | `Production Company`, `Distributor`, `data_as_of`, `data_loaded_at` |

The new dataset is now authoritative for the project. The old GeoPackage is retained on disk under its original filename for archival reference; nothing in the live pipeline reads from it.

---

## Why we swapped

Three reasons, in increasing order of weight.

**Feature unlock.** SFgov's December 2024 update added an `Analysis Neighborhood` column derived from point-in-polygon lookup against the official SF Planning neighborhood boundaries. This unlocks a query class the app has not been able to support — "films shot in North Beach," "films in the Sunset," etc. — which is one of the more natural ways non-technical users describe SF locations.

**Quality parity, then better.** Reconciliation (notebook: `SIMPLE_film_dataset_reconcillation_2026.ipynb`) compared 2,080 matched rows. 42% of geometries agreed within 20m. 21% within 100m. 9% within 250m. The remaining 24% were over 250m apart — initially worrying, but inspection showed clear structure: ~165 rows are span/range/intersection strings with no canonically correct point (both geocoders defensibly disagreed); ~245 rows are short-name landmarks where SFgov was consistently more accurate when one was clearly right (Alcatraz Island, Filbert Steps, Mel's Drive-In, etc., all checked manually). Five rows in the old dataset had catastrophic HERE failures — "Hamburger Haven" geocoded to Düsseldorf, "The Matrix skyline/exterior scenes" to Colombia, "Mason Street at Jackson" to Kansas City. The swap silently fixes these.

**Neighborhood column trustworthiness.** Spot-check audit of 40 rows across 8 well-known neighborhoods (North Beach, Mission, Sunset/Parkside, Marina, Tenderloin, Chinatown, Castro/Upper Market, Haight Ashbury), 5 rows each, found 39 of 40 correct. The single edge case (a *Sense8* "Market St. overpass" row tagged as Mission) traces to the Octavia & Market boundary point, where the SFgov polygon for "Mission" plausibly extends north to Market Street — defensible, consistent, rule-based. No systematic mislabeling found.

---

## What we accepted by swapping

**80 rows have blank geometry on the SFgov side.** Of these, 54 are pure new additions (films added since May 2025) where the location string didn't resolve to a single point, and 26 are previously-geocoded rows where SFgov declined to geocode where HERE had returned something.

The 26 are not arbitrary. Every one is a span, range, transit line, or multi-place description — strings like "Embarcadero between Market to Fillmore St," "BART from Civic Center to 24th St," "Hyde St and Lombard St to Larkin and Lombard," or "Muni line N-Judah." These do not correspond to single points. SFgov returning blank is the more honest answer; HERE's old behavior was to silently pick a defensible end of the span (often the first cross-street mentioned) and present it as the row's location.

**Decision: accept the blanks.** These rows still flow through the pipeline. They appear in Director, Writer, Actor, Year, Title, and Locations-text queries normally. They are excluded from:

- spatial radius queries (`films within X miles of Y`) — appropriate, because the row has no honest single point
- neighborhood queries — appropriate, because SFgov derives neighborhoods from geometry; no geometry, no neighborhood

This produces a self-consistent dataset: every row either has both point and neighborhood (both derived from the same SFgov geocoding pass), or has neither.

**144 rows have a point but no neighborhood.** These are points that fall outside SFgov's "Analysis Neighborhood" coverage — Alcatraz, Treasure Island (some rows), Golden Gate National Recreation Area, locations in the bay, "exterior scenes" tagged to skyline coordinates, etc. The point is valid; the neighborhood is correctly NaN because the location is outside the official neighborhood polygons. Spatial queries work on these rows; neighborhood queries do not. Same logic as above.

---

## Pipeline changes required (separate work)

This document records the data swap. The application changes are tracked separately and include:

- Schema reference: add `Neighborhood` and `Supervisor_District` columns to the GeoDataFrame columns list documented in code generation prompts
- Step 4 (Filter Extractor): add `Neighborhood` to allowed-fields list, add 1–2 few-shot examples for neighborhood queries
- Step 5 (Granularity Resolver): no change — neighborhood is a filter dimension, not a granularity option
- Step 1 (Query Normalizer): consider whether multi-word neighborhood names ("North Beach," "Russian Hill," "Pacific Heights," "Castro/Upper Market") need protection in the cluster extractor; the N-1 phrase pre-pass open item from `phase_3_open_items_April_26.md` is the right tool if so
- Test coverage: add T35–T40 (or equivalent next-phase numbering) covering neighborhood retrieves, neighborhood + cross-field AND, and neighborhood-based counts

---

## Deferred items

Tracked here so they don't get lost.

**26 rows with HERE-but-not-SFgov geometry.** Two of them — "47 Julian St" (San Andreas) and "284 Sanchez St" (The Phone/Jexi) — are clean street addresses that should resolve to single points; SFgov failing to geocode them looks like an artifact of the prefix text in the location string ("Stage Work, 47 Julian St.", "Mash Transit - 284 Sanchez St"). Could be patched manually for ~2 rows of additional spatial coverage. Optional, low priority.

The other 24 are span/transit/multi-place strings that genuinely don't resolve to a single point. Leaving them blank is correct.

**5 catastrophic HERE failures resolved by the swap.** Worth noting in the win column rather than as a deferred item: the old dataset placed *Hamburger Haven* (The Diary of a Teenage Girl) in Düsseldorf, *The Matrix* skyline shots in Colombia, *Plate Shots SF streets various* (Age of Adaline) also in Colombia, *Mason Street at Jackson* (Getting Even with Dad) in Kansas City. Spatial queries against the old dataset have been silently excluding these from any "near anywhere in SF" results for the past year. The swap fixes this.

**Market Street boundary cases.** Points near Octavia & Market and similar boundary zones may surface in queries against multiple neighborhoods depending on which side of the polygon line they fall. Not a fix item — this is how official boundaries work — but worth a one-line note in app copy or response style if a user query produces a confusing result. Suggested phrasing: neighborhood assignments use SF Planning's official boundary file, which sometimes differs from cultural neighborhood conventions, particularly along Market Street.

---

## Files

- New dataset: `Film_Locations_in_San_Francisco_20260424.csv` (2,214 rows × 18 cols)
- Old dataset (archived, read-only): `sf_film_May7_2025_data.gpkg` (2,084 rows × 11 cols)
- Reconciliation notebook: `SIMPLE_film_dataset_reconcillation_2026.ipynb`
- Reconciliation outputs: `high_priority_geometry_review.csv` (779 rows of disagreements), supporting CSVs in the reconciliation_outputs directory


# Conversion Refinements — Addendum

The conversion from SFgov CSV to canonical GeoPackage went through several refinements before producing the final file. Recording them here for the trail.

## Changes applied during conversion

**Columns dropped:** `Point` (redundant WKT string), `data_as_of` and `data_loaded_at` (SFgov bookkeeping, same value on every row), `Longitude` and `Latitude` (redundant once geometry column exists; geometry is the source of truth).

**Columns renamed** to project snake_case convention: `Release Year` → `Year`, `Fun Facts` → `Fun_Facts`, `Production Company` → `Production_Company`, `Actor 1/2/3` → `Actor_1/2/3`, `Analysis Neighborhood` → `Neighborhood`, `Supervisor District` → `Supervisor_District`. `Distributor` kept as-is.

**Numeric types corrected.** `Year` and `Supervisor_District` cast from `float64` to nullable `Int64`. They are categorically integers; the float dtype was a pandas artifact of holding NaN. Display now reads `2008` not `2008.0`, and equality checks behave like integers.

**Geometry built** from Longitude/Latitude as `Point(lon, lat)`, null-safe (rows without coordinates get null geometry), wrapped in `EPSG:4326`.

**Street suffixes normalized** on the `Locations` column at conversion time using the same function the pipeline uses at query time. Baked into the file so future loads don't need to re-normalize.

**Exact duplicates dropped.** SFgov's source CSV contained 13 rows in 6 duplicate groups. Dedup applied across all content columns (not just `Title + Year + Locations`) to preserve the *San Andreas* / AT&T Stadium case where two rows share location but have different `Fun_Facts` (different scenes filmed at the same site). Net effect: 6 exact-duplicate rows removed, 1 semantically distinct duplicate preserved.

## Final canonical file

- Path: `data-reconcillation-2026/sf_film_2026_04_24_data.gpkg`
- Shape: **2,208 rows × 14 columns**
- CRS: `EPSG:4326`
- Geometry null: 86 rows (span/transit/multi-place strings SFgov declined to geocode)
- Neighborhood null: 144 rows (points outside official SF Planning neighborhood polygons — Alcatraz, Treasure Island, GGNRA, etc.)
- Unique films: 352

## Decisions deferred

NaN/null values were *not* converted to empty strings. Null and empty string mean different things ("data absent" vs "data present and empty"); conflating them silently breaks `notna()` filters and pandas aggregations. Display-side handling at the print/format site is the right place to address null cosmetics.

Object-vs-string dtype for text columns left as `object`. The GeoPackage format doesn't preserve the distinction across write/read round-trips, so the change wouldn't survive anyway.

## Conversion script

Saved alongside this document as `convert_sfgov_csv_to_geopackage.py`. Re-runnable if SFgov updates the source CSV; all column-renaming, type-casting, normalization, and dedup decisions are baked in.