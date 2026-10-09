# Issue tracker: GitHub

Issues and specs live in ajs-02/ecommerce-churn-pipeline.
Use the gh CLI with --repo ajs-02/ecommerce-churn-pipeline.

- Create issues with gh issue create.
- Read issues with gh issue view, including body, labels and comments.
- List issues with gh issue list and appropriate state and label filters.
- Apply or remove labels with gh issue edit.
- Comment with gh issue comment; close with gh issue close.
- For multiline text, use a temporary file and --body-file.

When a skill says to publish to the issue tracker, create a GitHub issue.
When it says to fetch a ticket, read the corresponding GitHub issue.

## Pull requests as a triage surface

PRs as a request surface: no.

## Wayfinding

Use one map issue labelled wayfinder:map.
Link child tickets as GitHub sub-issues when supported.
Otherwise, list children in the map and put Part of #<map> in each child.
Use wayfinder:<type> labels for research, prototype, grilling and task.
Record blockers with native issue dependencies when supported.
Otherwise, put Blocked by: #<number> in the child.
Select an open, unassigned child with no open blockers, in map order.
Claim it by assigning yourself.
After resolution, close the child and record its result and link in the map.
