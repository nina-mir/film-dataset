"""
Extract the rows where HERE (old dataset) provided a geometry but SFgov
(new dataset) returned blank.

Source: high_priority_geometry_review.csv (output of the reconciliation
notebook). This file contains the 779 matched-pair rows where geometry
review was warranted — distance > 100m, or one side missing geometry.

The 26 rows isolated below are the ones discussed in dataset_swap_2026.md
under "26 rows with HERE-but-not-SFgov geometry" — span/transit/multi-place
strings that SFgov declined to geocode but HERE returned a point for.

Output: a CSV with one row per case, sorted by Title then Year.
"""

from pathlib import Path

import pandas as pd

# --- Paths ---------------------------------------------------------------

# Adjust if running outside the project root.
INPUT_PATH = Path('high_priority_geometry_review.csv')
OUTPUT_PATH = Path('here_only_geometry_rows.csv')


# --- Load ----------------------------------------------------------------

df = pd.read_csv(INPUT_PATH)
print(f'Loaded {len(df)} rows from {INPUT_PATH.name}')


# --- Filter: HERE has geometry, SFgov does not ---------------------------
#
# The reconciliation notebook stored two boolean flags per matched row:
#   has_old_geometry — HERE-side point present
#   has_new_geometry — SFgov-side point present
#
# We want the rows where the first is True and the second is False.

mask = (df['has_old_geometry'] == True) & (df['has_new_geometry'] == False)
here_only = df.loc[mask].copy()

print(f'Rows with HERE-only geometry: {len(here_only)}')


# --- Select and order the columns useful for review ----------------------
#
# Drop the duplicated _new fields (they're empty for these rows by
# definition) and the bookkeeping columns. Keep the HERE-side data plus
# the matching key, so each row is self-explanatory at a glance.

review_cols = [
    'Title_old',
    'Year_old',
    'Locations_old',
    'geometry_old',          # the HERE point we may or may not want to keep
    'Director_old',
    'Writer_old',
    'Actor_1_old',
    'Actor_2_old',
    'Actor_3_old',
    'Fun_Facts_old',
    'match_key',
]

here_only = here_only[review_cols].sort_values(
    ['Title_old', 'Year_old']
).reset_index(drop=True)


# --- Write ---------------------------------------------------------------

here_only.to_csv(OUTPUT_PATH, index=False)
print(f'Wrote {len(here_only)} rows to {OUTPUT_PATH}')


# --- Quick preview -------------------------------------------------------

pd.set_option('display.max_colwidth', 80)
pd.set_option('display.width', 200)

print()
print('Preview:')
print(here_only[['Title_old', 'Year_old', 'Locations_old', 'geometry_old']].to_string(index=False))
