# first results of tests t1-10 results

## APRIL-17



############################################################
  TEST 1/10: T1: Retrieve by Director (string ==)
  Query: films directed by alfred hitchcock
  Expected: retrieve, film granularity, Director predicate
############################################################

============================================================
Query: films directed by alfred hitchcock
============================================================

[Step 1] Normalized: films directed by alfred hitchcock
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films directed by alfred hitchcock",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  [filter_extractor] Error: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}, null predicates fallback
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films directed by alfred hitchcock",
      "dependsOn": [],
      "predicate": null
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 261 chars
  Prompt size: 53865 chars
  ✓ Code generated: 1812 chars
  Explanation: The `process_sf_film_query` function takes a GeoDataFrame as input. It creates a copy to avoid modifying the original. For Task t1, since the `predica...

============================================================
Pipeline ✗ FAILED
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 2/10: T2: Retrieve by Location (contains)
  Query: films shot on market street
  Expected: retrieve, film granularity, Locations contains
############################################################

============================================================
Query: films shot on market street
============================================================

[Step 1] Normalized: films shot on market street
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films shot on market street",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films shot on market street",
      "dependsOn": [],
      "predicate": {
        "field": "Locations",
        "op": "contains",
        "value": "market street",
        "type": "attribute"
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 377 chars
  Prompt size: 53981 chars
  ✓ Code generated: 3975 chars
  Explanation: The `process_sf_film_query` function takes a GeoDataFrame as input. It first creates a copy to ensure no mutations to the original data. For task `t1`...

============================================================
Pipeline ✗ FAILED
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 3/10: T3: Retrieve by Actor (virtual field)
  Query: films with sean penn
  Expected: retrieve, film granularity, Actor OR expansion
############################################################

============================================================
Query: films with sean penn
============================================================

[Step 1] Normalized: films with sean penn
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films with sean penn",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films with sean penn",
      "dependsOn": [],
      "predicate": {
        "logic": "OR",
        "clauses": [
          {
            "field": "Actor_1",
            "op": "==",
            "value": "sean penn",
            "type": "attribute"
          },
          {
            "field": "Actor_2",
            "op": "==",
            "value": "sean penn",
            "type": "attribute"
          },
          {
            "field": "Actor_3",
            "op": "==",
            "value": "sean penn",
            "type": "attribute"
          }
        ]
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 746 chars
  Prompt size: 54350 chars
  ✓ Code generated: 3612 chars
  Explanation: The `process_sf_film_query` function executes the query to find films starring Sean Penn. It first creates a copy of the input GeoDataFrame to avoid m...

[Execution] ✓ Success
  Summary: Found 5 films with Sean Penn.
  Data: [{'id': 68, 'Title': 'The Game', 'Year': 1997, 'Locations': 'Sheraton Palace Hotel (639 Market Street)', 'Fun_Facts': 'The hotel was destroyed in the 1906 earthquake and fire, had to be rebuilt, and w

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 4/10: T4: Count films in a decade
  Query: how many films were shot in the 80s
  Expected: count, scalar granularity, Year between 1980-1989
############################################################

============================================================
Query: how many films were shot in the 80s
============================================================

[Step 1] Normalized: how many films were shot in the 80s
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "count",
      "source": "how many films were shot in the 80s",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "count",
      "source": "how many films were shot in the 80s",
      "dependsOn": [],
      "predicate": {
        "field": "Year",
        "op": "between",
        "value": [
          1980,
          1989
        ],
        "type": "attribute"
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=scalar, offer_map=False
  Top-level offer_map: False

[Step 6] Generating code...
  IR size: 407 chars
  Prompt size: 54011 chars
  ✓ Code generated: 3521 chars
  Explanation: ...

[Execution] ✓ Success
  Summary: There were 39 films shot in the 1980s.
  Data: 39

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 5/10: T5: Rank directors by film count
  Query: top 5 directors with the most films
  Expected: rank, film granularity, no predicate filter (null or all rows)
############################################################

============================================================
Query: top 5 directors with the most films
============================================================

[Step 1] Normalized: top 5 directors with the most films
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "top 5 directors with the most films",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "top 5 directors with the most films",
      "dependsOn": [],
      "predicate": null
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 262 chars
  Prompt size: 53866 chars
  ✓ Code generated: 3626 chars
  Explanation: ...

[Execution] ✓ Success
  Summary: The top 5 directors with the most films are: Andrew Haigh: 11 films; Chris Columbus: 4 films; Philip Kaufman: 4 films; Alfred Hitchcock: 4 films; Garry Marshall: 4 films.
  Data keys: ['Andrew Haigh', 'Chris Columbus', 'Philip Kaufman', 'Alfred Hitchcock', 'Garry Marshall']

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 6/10: T6: Retrieve by Year (exact)
  Query: films from 1985
  Expected: retrieve, film granularity, Year == 1985
############################################################

============================================================
Query: films from 1985
============================================================

[Step 1] Normalized: films from 1985
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films from 1985",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films from 1985",
      "dependsOn": [],
      "predicate": {
        "field": "Year",
        "op": "==",
        "value": 1985,
        "type": "attribute"
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 343 chars
  Prompt size: 53947 chars
  ✓ Code generated: 3231 chars
  Explanation: The code defines a function `process_sf_film_query` that takes a GeoDataFrame. It first creates a copy of the input DataFrame to ensure no mutations. ...

[Execution] ✓ Success
  Summary: Found 4 unique films from 1985.
  Data: [{'id': 4, 'Title': 'A View to a Kill', 'Year': 1985, 'Locations': "Taylor and Jefferson Streets (Fisherman's Wharf)", 'Fun_Facts': '', 'Director': 'John Glen', 'Writer': 'Richard Maibaum', 'Actor_1':

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 7/10: T7: Retrieve by Director + Year range (AND)
  Query: films by alfred hitchcock from the 1950s
  Expected: retrieve, film granularity, Director AND Year between
############################################################

============================================================
Query: films by alfred hitchcock from the 1950s
============================================================

[Step 1] Normalized: films by alfred hitchcock from the 1950s
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films by alfred hitchcock from the 1950s",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films by alfred hitchcock from the 1950s",
      "dependsOn": [],
      "predicate": {
        "logic": "AND",
        "clauses": [
          {
            "field": "Director",
            "op": "==",
            "value": "alfred hitchcock",
            "type": "attribute"
          },
          {
            "field": "Year",
            "op": "between",
            "value": [
              1950,
              1959
            ],
            "type": "attribute"
          }
        ]
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 673 chars
  Prompt size: 54277 chars
  ✓ Code generated: 3869 chars
  Explanation: The code defines a function `process_sf_film_query` that takes a GeoDataFrame `gdf`. It first creates a copy of the input GeoDataFrame to ensure no mu...

[Execution] ✓ Success
  Summary: Found 1 films directed by Alfred Hitchcock from the 1950s.
  Data: [{'id': 34, 'Title': 'Vertigo', 'Year': 1958, 'Locations': '1007 Gough Street', 'Fun_Facts': "Tennis courts now sit on the site; in the movie the structure was Carlota Valdes' home.", 'Director': 'Alf

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 8/10: T8: Spatial retrieve (within_distance)
  Query: films within 1 mile of coit tower
  Expected: retrieve, location granularity, geometry within_distance
############################################################

============================================================
Query: films within 1 mile of coit tower
============================================================

[Step 1] Normalized: films within 1 mile of coit tower
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films within 1 mile of coit tower",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "films within 1 mile of coit tower",
      "dependsOn": [],
      "predicate": {
        "field": "geometry",
        "op": "within_distance",
        "value": {
          "reference_place": "coit tower",
          "distance": 1,
          "unit": "mile",
          "latitude": 37.8024,
          "longitude": -122.4058
        },
        "type": "spatial"
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 541 chars
  Prompt size: 54145 chars
  ✓ Code generated: 6326 chars
  Explanation: The code defines a function `process_sf_film_query` that takes a GeoDataFrame as input. It first creates a copy of the input GeoDataFrame to avoid mod...

[Execution] ✓ Success
  Summary: Error processing query: 'predicate'

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 9/10: T9: Retrieve locations for a film
  Query: show filming locations for vertigo
  Expected: retrieve, location granularity, Title contains vertigo
############################################################

============================================================
Query: show filming locations for vertigo
============================================================

[Step 1] Normalized: show filming locations for vertigo
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "show filming locations for vertigo",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "show filming locations for vertigo",
      "dependsOn": [],
      "predicate": {
        "field": "Title",
        "op": "==",
        "value": "vertigo",
        "type": "attribute"
      }
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=location, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 372 chars
  Prompt size: 53976 chars
  ✓ Code generated: 3436 chars
  Explanation: The code defines a function `process_sf_film_query` that takes a GeoDataFrame as input. It first creates a copy of the input to avoid modifying the or...

[Execution] ✓ Success
  Summary: Found 16 filming locations for 'Vertigo'.
  Data: [{'id': 34, 'Title': 'Vertigo', 'Year': 1958, 'Locations': '1007 Gough Street', 'Fun_Facts': "Tennis courts now sit on the site; in the movie the structure was Carlota Valdes' home.", 'Director': 'Alf

============================================================
Pipeline ✓ SUCCESS
============================================================

  ⏳ Waiting 2s before next test...

############################################################
  TEST 10/10: T10: Rank actors by film count in decade
  Query: actors who appeared in the most films in the 90s
  Expected: rank, film granularity, Year between 1990-1999
############################################################

============================================================
Query: actors who appeared in the most films in the 90s
============================================================

[Step 1] Normalized: actors who appeared in the most films in the 90s
[Step 2] Safe ✓

[Step 3] Decomposing...
  Tasks: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "actors who appeared in the most films in the 90s",
      "dependsOn": []
    }
  ]
}

[Step 4] Extracting filters...
  [filter_extractor] Error: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash\nPlease retry in 21.04569123s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '21s'}]}}, null predicates fallback
  Filters: {
  "tasks": [
    {
      "id": "t1",
      "kind": "retrieve",
      "source": "actors who appeared in the most films in the 90s",
      "dependsOn": [],
      "predicate": null
    }
  ]
}

[Step 5] Presentation resolved:
  t1: granularity=film, offer_map=True
  Top-level offer_map: True

[Step 6] Generating code...
  IR size: 275 chars
  Prompt size: 53879 chars

❌ Code generation failed: Code generation failed: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash\nPlease retry in 4.807049632s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '4s'}]}}


============================================================
TEST SUITE SUMMARY
============================================================
  Passed: 7/10
  Failed: 3/10

  ✗ T1: Retrieve by Director (string ==)
    → Execution error: Validation failed: Syntax error: expected 'except' or 'finally' block (<unknown>, line 31)
  ✗ T2: Retrieve by Location (contains)
    → Execution error: Validation failed: Syntax error: unterminated f-string literal (detected at line 62) (<unknown>, lin
  ✓ T3: Retrieve by Actor (virtual field)
  ✓ T4: Count films in a decade
  ✓ T5: Rank directors by film count
  ✓ T6: Retrieve by Year (exact)
  ✓ T7: Retrieve by Director + Year range (AND)
  ✓ T8: Spatial retrieve (within_distance)
  ✓ T9: Retrieve locations for a film
  ✗ T10: Rank actors by film count in decade
    → Codegen error: Code generation failed: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded you


## APRIL-18


T5 genrated code:

import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

def process_sf_film_query(gdf):
    """
    Execute a read-only query against the SF film locations GeoDataFrame.
    Returns a standardized result dictionary.
    """
    def clean_column_data(series):
        """Remove empty/null/whitespace/stringy-null values from a string Series.

        WARNING: Returns a FILTERED series with fewer rows.
        Use ONLY for final output cleanup, NEVER for building boolean masks.
        """
        stringified = series.astype(str)
        exclude = (
            series.isna() |
            (stringified.str.strip() == '') |
            (stringified.str.lower().isin(['none', 'nan', 'null']))
        )
        return series[~exclude]

    try:
        gdf_copy = gdf.copy()
        task_results = {}

        # ── Task t1: top 5 directors with the most films ────────────────
        # No predicate, so matched_rows is the entire dataframe.
        t1_matched_rows = gdf_copy

        # For ranking directors by films, first deduplicate to film level.
        t1_film_df = t1_matched_rows.drop_duplicates(subset=["Title", "Year"], keep="first")

        # Clean and count directors
        director_counts = (
            t1_film_df["Director"]
            .dropna()
            .astype(str)
            .str.strip()
        )
        director_counts = director_counts[director_counts != ""]
        director_counts = director_counts[~director_counts.str.lower().isin(["none", "nan", "null"])]
        director_counts = director_counts.value_counts()

        # Take top N=5
        N_t1 = 5
        top_directors_t1 = director_counts.head(N_t1)

        task_results["t1"] = {
            "matched_rows": t1_matched_rows,
            "text_view": None, # Ranking tasks typically don't have a text_view in the same way retrieve tasks do
            "result": {
                "ranking": top_directors_t1.to_dict(),
                "rank_dimension": "directors",
                "rank_basis": "films",
                "N": N_t1,
            }
        }

        # ── Assemble final result ──────────────────────────────────────
        final_ranking = task_results["t1"]["result"]["ranking"]
        summary_parts = [f"{director}: {count} films" for director, count in final_ranking.items()]
        summary_str = f"The top {N_t1} directors with the most films are: {'; '.join(summary_parts)}."

        result = {
            'data': final_ranking.to_dict(),
            'summary': summary_str,
            'metadata': {
                'query_type': 'rank',
                'task_count': 1,
                'task_ids': ['t1'],
                'offer_map': True
            }
        }

        # ── Log (UTF-8 safe) ──────────────────────────────────
        with open('code_gen_result.log', 'a', encoding='utf-8', errors='replace') as f:
            f.write('=' * 50 + '\n')
            f.write('Query Result\n')
            f.write('-' * 50 + '\n')
            if isinstance(result['data'], (pd.DataFrame, gpd.GeoDataFrame)):
                f.write(result['data'].to_string() + '\n')
            else:
                f.write(str(result['data']) + '\n')
            f.write(f"Summary: {result['summary']}\n")
            f.write('=' * 50 + '\n\n')

        return result

    except Exception as e:
        error_result = {
            'data': None,
            'summary': f"Error processing query: {str(e)}",
            'metadata': {
                'error': str(e),
                'error_type': type(e).__name__
            }
        }
        with open('code_gen_result.log', 'a', encoding='utf-8', errors='replace') as f:
            f.write('=' * 50 + '\n')
            f.write(f'ERROR: {str(e)}\n')
            f.write('=' * 50 + '\n\n')
        return error_result

=========================================

T