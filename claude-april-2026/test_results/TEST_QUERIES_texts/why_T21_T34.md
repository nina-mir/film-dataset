# T21–T28 pressure Step 4 semantics without needing future schema changes. They cover:

* Director + Location
* Writer + Title
* Actor + Title
* cross-field OR
* output-dimension discipline
* Title/Location combinations
* Fun_Facts-adjacent wording
  All of that stays within the current allowed fields and mapping rules. 

T29–T34 push the dependency model harder:

* plain retrieve→count
* film-count vs location-count disambiguation
* child-task narrowing on dependency subset
* retrieve→rank within subset
* retrieve→retrieve→compare
* wording that could tempt the pipeline to confuse locations with films
  Those are exactly the patterns the codegen prompt says should work through `dependsOn` + `matched_rows` reuse. 

A few notes before you run them:

* T32 is especially useful because it pressures the known Step 3 rank-label weakness while still being a legitimate dependency test. If it answers correctly but labels the task as `retrieve`, that is still diagnostic of B3. 
* T26 and T27 are good “constraint vs output dimension” probes, which Step 4 explicitly treats as a central design rule. 
* T33 is the first one here that really tests whether your compare path is semantically stable rather than just present in the prompt spec. The codegen docs describe compare as later-phase and not yet primary coverage, so this is a useful frontier test. 

My recommendation is:
run **T21–T28 first** as a semantic mini-batch, then **T29–T34** as the dependency batch. That split will make it much easier to tell whether a failure is “predicate extraction logic” or “dependency/codegen orchestration.”
