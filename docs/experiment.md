# Run a feedback trial

Use a repository that is authorized to receive the trial data. This lab is
public, so all source data and proposals must be synthetic. Create the label
`improvement-candidate` once before testing publication:

```shell
gh label create improvement-candidate --repo OWNER/REPO --description "Project improvement pending human triage" --color 1d76db
```

## Work on an issue

1. Create a GitHub issue for a planner change. Give Copilot its number and
   acceptance criteria. Use Agent mode in Visual Studio or a Copilot CLI
   session in the checkout.
2. Ask Copilot to implement and run the [planner checks](../README.md#run-the-planner).
   In Visual Studio, enable repository custom instructions. The task-end
   instruction asks for a postmortem, but it does not guarantee execution.
3. If the handoff does not mention a draft or an explicit no-candidate result,
   ask in the **same chat**: “Apply the session-postmortem skill to this task.”
   Visual Studio can also run the [reusable prompt](../.github/prompts/postmortem.prompt.md).
   The same chat matters because the skill does not retrieve closed sessions.

## Publish a local candidate

Inspect the draft before sending it anywhere. Replace `12` with the work
issue number and `OWNER/REPO` with the intended GitHub repository. The publish
command requires a matching `origin`, an authenticated `gh`, issue write
permission, and the label created above.

```shell
python -B scripts/feedback.py preview .feedback/task-12.json --repo OWNER/REPO
python -B scripts/feedback.py publish .feedback/task-12.json --repo OWNER/REPO
```

`preview` is offline. `publish` creates a candidate with a backlink to the
work issue. It records the issue number in `.feedback/receipts/`. A serial
retry from the same checkout looks up that number directly, even if the
labeled issue list has not refreshed yet. Keep the label on triaged items so
other checkouts and workflow reruns can find them. Do not publish the same
source concurrently from different machines.

## Merge a reviewed PR

1. Open a PR from a branch in the same repository and link the work issue.
2. Wait for Planner CI. Request GitHub Copilot code review with
   `gh pr edit PR_NUMBER --repo OWNER/REPO --add-reviewer @copilot` if your
   plan permits it. A human or an independently run agent can also leave a
   review. Record observations that would help future changes.
3. As the repository owner, merge into `main` after review finishes. PR
   Feedback reads review bodies, inline comments, check results, and changed
   paths. It accepts a valid [structured review](../REVIEW.md) from Copilot
   or the owner. It can also confirm the planner-specific profile coverage gap
   by comparing the review, changed paths, and CI configuration. The publish
   job adds the label and links the source PR and review.
4. Re-run a positive workflow once to verify that it returns the same issue.
   Merge a clean PR to verify that it leaves no candidate. Closing without
   merging and merging a fork PR do not trigger publication.

The markers deduplicate retries from the same source; they do not merge
similar findings across different issues or PRs. Triage those together and
choose whether to update documentation, standards, CI, or Copilot instructions.
