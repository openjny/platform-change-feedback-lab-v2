# Planner review

When a PR adds a profile, inspect the Planner CI workflow and its test
discovery. Report a reusable CI gap only if the new profile is not covered.
Do not treat passing unit tests as evidence that every profile was validated.

For a concrete process improvement that applies to future PRs, you may put a
fenced `platform-feedback` JSON object in your review. Use `category`
(`docs`, `instructions`, `standard`, or `lint-ci`), `title`, `finding`, and
`suggestion`. Keep those fields on one line each, without Markdown inside the
values. Describe evidence from this PR. Do not write a candidate if the PR has
no process issue. Do not use the format for changes needed only in this PR.
