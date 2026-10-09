# Require personal selection before final test evaluation

Accepted 8 October 2026. Use random stratified 60/20/20 partitions and training-only ten-fold CV, then let the user select candidates/thresholds from development evidence. Freeze all candidates before evaluating the selected model first and then alternatives on the final test and uncertain cohorts. Alternative test results are preserved as history rather than used to retune or silently replace the choice. The same training-fitted pipelines score every cohort, keeping the reviewed model identical to the final evaluated model.
