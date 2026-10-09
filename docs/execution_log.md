# Execution decisions and evidence

## User delegation, 9 October 2026

The user approved committing, pushing and merging T02, then continuous execution of T03, T04 and T05 until resolved and all required tests pass. The user explicitly overrode personal task-review stops and delegated routine questions to agent judgment, requiring durable documentation. This authorization supersedes the project documents' task review gates only for T03 through T05. It does not approve a model candidate, fabricate a model decision record, or authorize T06 through T08.

T02 was merged through PR11 and reader-lifetime follow-up PR12. The post-fix suite passed 75 checks.

## T03

Issue #4, Complete typed dbt staging and aggregate payment shares. Separate managed worktree and branch codex/t03-typed-staging. Starting commit 3aa973c1606e651c856ee3336345d3fdebd5116a; rebased onto current dev 0fe70e0205d618c4593b7dbf990d5ec4c5261c48 after PR12.

Delegated public test seam is the real dbt run/test/docs CLI and SELECT of staged relations in disposable PostgreSQL. It catches staging schema, deterministic aggregate outputs and integrity rejection. It does not assert private compilation helpers, production data quality or future model choices. No live configured target was used. Tests use trust-authenticated local t02/postgres at 127.0.0.1:55433 and reset only this disposable schema.

Red-green evidence: split voucher 30+30 versus card 50 incorrectly chose card, then correctly chose voucher and total110. Legacy raw product dimensions supplied as text exposed missing casts, then became numeric. Negative payment -1 plus positive20 previously had no selected check; a raw-payment dbt check now fails before this error can be hidden by aggregation.

Money nulls remain staged as unknown for T04 eligibility. Staging not-null money checks were removed because they contradicted specification section4.2; negative/non-finite checks remain hard failures. C collation makes payment ties independent of host locale. Unknown types are not filled. PostgreSQL typed booleans cannot represent arbitrary strings; accepted_values uses unquoted true/false literals.

Item monetary casts use unbounded numeric after fixture123456789.123 and freight0.001 demonstrated overflow/rounding under the previous numeric10,2. Explicit staging tests use cautious indirect selection so unrelated unbuilt mart assertions cannot create false failures.

Detailed fixture inputs, commands, outcomes, dependencies and dbt docs artifacts are preserved outside the managed worktree under C:/Users/prince/.codex/visualizations/2026/10/09/01a11faf-27a8-7441-a7ba-1c98add13e78/pipeline-evidence/t03. Review packet records actual final results.

T03 review identified two additional boundary cases. Legacy text lowercase nan/infinity is normalized through a numeric cast before the dbt non-finite check. A null voucher amount competing with card50 keeps total and favorite unknown while voucher remains true. Both regressions were reproduced first, then fixed through the same dbt/SELECT seams.

Final T03 validation on 9 October 2026:98 passed,0 skipped,1 intentional duplicate-archive fixture warning in301.06 seconds. Command was .venv/Scripts/python.exe -m pytest -q with T02_POSTGRES_PORT and T03_POSTGRES_PORT both55433. PostgreSQL acceptance checks were enabled. dbt staging run/test/docs, formatting, Python compilation and git diff checks pass. Coordinator Standards and Spec reviews found zero unresolved findings after two reproduced regression fixes. T03 is resolved under the user's delegated acceptance instruction and ready for publication to dev.

## T04 planned execution

Issue #5. Branch codex/t04-repeat-features, starting commit 5db3046cb1fe4fe50378bbfef62bf5b82d6711c4. Separate disposable PostgreSQL on127.0.0.1:55434; no configured live target.

User-delegated test seams are real dbt run/build/test/docs and SELECT customer_features/customer_feature_diagnostics, plus the public export_feature_diagnostics CLI. These observe selected feature values, original timestamps, target labels, retained warnings and reconciling census. They do not depend on private compiler helpers. The user's instruction to exercise best judgment replaces confirmation stops for these T04 interfaces.

Planned vertical slices: literal fractional seconds and calendar lateness/recency (FEAT07-09,17-18); deterministic anchors and all-status inclusive target (FEAT01-03,TGT01-05); financial/item/review identities and unknown constituents (FEAT04-06,10-12,19); negative elapsed exclusions and warning overlaps (FEAT13-14); hard monetary/configuration checks and legitimate zeros (FEAT15-16); shared diagnostic export counts. Every slice records a red failure before its implementation. Fixtures use timezone-naive timestamps. Config defaults derive from all-order maximum; an observation override earlier than any recorded purchase and as_of_date earlier than any anchor date fail build. Configuration is metadata, not a predictor.

Diagnostic relation contains exactly one candidate per first-delivered customer before exclusion. Mart selects its eligible rows. Reason arrays represent overlaps and pattern arrays identify mutually exclusive combinations. Original event timestamps, recovered spend and null unknowns remain visible. Export includes all/eligible/excluded target classes, early positives and warning counts so T05 can reuse the same census rather than recalculate eligibility.

T04 baseline passed98tests with0skips and1intentional duplicatearchivewarning in336.60seconds. Eleven vertical slices recorded redbeforegreen under artifacts/t04: seconds; deterministic anchor/target; financialunknowns; chronology; invalidconfiguration; rawmonetarypublicationguard; legitimatezeros/tolerance; exactmaturity/validanchoroverride; numericmartchecks; diagnosticexport; plausibleincorrectmartidentity. Configslice exposed a singletonbug whenboth overrideswereexplicit; settings now remainsone row. The validasof test also proved recencyguard mustuseanchor dates ratherthanlater deliveredorders. Raw money guard executes before diagnostic materialization so dbt run cannot publish valid-looking features after disconnectedtestfailures. Existing source tests remain.

Export public interface: python scripts/export_feature_diagnostics.py --output-dir <path>, writing census.json and bounded candidates-*.parquet. The aggregate loader load_feature_census(connection) is reusable by T05. Repeatable-read extraction keeps census and rowsconsistent; overlaps liveinreasoncounts, patterncounts count eachcustomeronce. Unknown/absentpayment cases preserved; recoveredflagtrue onlywhen fallback yieldsknownspend. Customer-level exports stayignored.

Validation inprogress: final fullsuite, real fullCSVcensus and coordinator code review. No taskaccepted orpublished bythisworker. Disposable database recreated UTF8/C for sourceunicode portability; timestamps remainwithout timezone independently of servertimezone. PowerBI unchanged.

T04 first full suite found120passing tests andonefixture failure in518.43seconds. The globalreview fixture accidentally reused the existing review_id, so required staged deduplication correctly removed the later score5. Correcting the distinct review identity, rather than changing global average logic, restores the intended independent mean4 versus anchoronlymean3 case. Actual failure log retained.

T04 independent Standards review found partial export failure could replace Parquet files while stale census.json remained. Public export filesystem fault reproduced the damaged prior snapshot. Export now stages a complete sibling directory and promotes it only after repeatable-read extraction completes, with prior-directory rollback on promotion failure. The previous valid snapshot survives write failure; directory promotion has the same brief path-unavailable window as acquisition. Backup remains outside temporary cleanup if restoration fails. The stale dbt README is corrected. Independent Spec review found no missing or incorrect code requirements. The corrected reviewthresholdfixture and export regression pass; originalfailedsuite and interruptedrun remain separate evidence.
