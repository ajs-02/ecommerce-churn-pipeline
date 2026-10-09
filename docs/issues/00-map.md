# Complete the agreed Olist exploratory implementation

The user confirmed the design interview on 8 October 2026. This map tracks the remaining implementation, not authorization to begin coding. The agreed contracts are published on the dev branch. Implementation still awaits the user's task-plan review.

Read [the spec](https://github.com/ajs-02/ecommerce-churn-pipeline/blob/dev/docs/project_spec.md), [the implementation plan](https://github.com/ajs-02/ecommerce-churn-pipeline/blob/dev/docs/implementation_plan.md), [the acceptance matrix](https://github.com/ajs-02/ecommerce-churn-pipeline/blob/dev/docs/test_acceptance_matrix.md) and `docs/implementation_gap.md` before implementation. Use the task plan as the source of detailed handoff steps and proposed search spaces.

All children start unassigned with `needs-triage` pending the user's plan review. Subagents deliver outputs, test cases and outcomes; only the user accepts a task. Accepted prerequisites are required before dependent work. Model/threshold selection is a separate human gate before test evaluation.

Task order: T01 acquisition -> T02 atomic upload -> T03 staging -> T04 features/target -> T05 profiles/EDA -> T06 experiments -> T07 gate/history -> T08 final verification.

No Power BI edits, weekly/push training, deployment, synthetic future data, fitted calibration or information-arrival audit in this scope. Optional later classifiers require runtime/results review.

## Published tasks

All eight tasks are native sub-issues of this map, with native blocker dependencies in the listed order. Textual references in each child also preserve the relationship.

| Task | Issue | Blocked by |
| --- | --- | --- |
| T01 | [#2](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/2) | User plan approval |
| T02 | [#3](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/3) | #2 |
| T03 | [#4](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/4) | #3 |
| T04 | [#5](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/5) | #4 |
| T05 | [#6](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/6) | #5 |
| T06 | [#7](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/7) | #6 |
| T07 | [#8](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/8) | #7 |
| T08 | [#9](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/9) | #8 |

Acceptance requires the user's review; an open blocker also prevents dependent implementation. No task is assigned or accepted by publication.
