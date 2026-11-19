import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.feedback import candidate, classify, event_pr, evidence_url, publish, publish_local, render

REPO = "example/platform-change-feedback-lab"
PR = f"https://github.com/{REPO}/pull/3"
DATA = {
    "category": "lint-ci",
    "title": "Validate every profile in CI",
    "finding": "A new checked-in profile was not covered by the smoke check.",
    "suggestion": "Run the validator on every checked-in profile.",
}


class FeedbackTests(unittest.TestCase):
    def test_structured_review_must_come_from_owner_or_copilot(self):
        body = "```platform-feedback\n" + json.dumps(DATA) + "\n```"
        item = {"author": "untrusted", "kind": "review", "text": body, "url": PR}
        self.assertIsNone(classify([item], [], "", "example"))
        item["author"] = "copilot-pull-request-reviewer[bot]"
        proposal = classify([item], [], "", "example")
        self.assertEqual(proposal["candidate"], DATA)
        self.assertEqual(proposal["evidence"], PR)

    def test_profile_rule_requires_change_review_and_ci_gap(self):
        ci = "      - run: python -B plan.py profiles/dev.json\n"
        item = {
            "author": "example", "kind": "review", "url": PR,
            "text": "CI checks profiles/dev.json but does not check the new profile.",
        }
        files = [{"filename": "profiles/test.json", "status": "added"}]
        self.assertEqual(classify([item], files, ci, "example")["candidate"]["category"], "lint-ci")
        self.assertIsNone(classify([item], [], ci, "example"))
        self.assertIsNone(classify([], files, ci, "example"))
        self.assertIsNone(classify([item], files, "- run: python -B -m unittest", "example"))

    def test_reject_content_that_would_ping_or_link(self):
        with self.assertRaises(ValueError):
            candidate({**DATA, "finding": "@somebody please check"})
        with self.assertRaises(ValueError):
            evidence_url("https://github.com/elsewhere/project/pull/3", REPO, 3)

    def test_reject_fork_or_unmerged_pr(self):
        pr = {"merged": True, "base": {"ref": "main"}, "head": {"repo": {"full_name": REPO}}}
        event = {"action": "closed", "pull_request": pr, "sender": {"login": "example"}}
        self.assertEqual(event_pr(event, REPO), pr)
        pr["head"]["repo"]["full_name"] = "fork/project"
        with self.assertRaises(ValueError):
            event_pr(event, REPO)
        pr["head"]["repo"]["full_name"] = REPO
        pr["merged"] = False
        with self.assertRaises(ValueError):
            event_pr(event, REPO)

    @patch("scripts.feedback.gh")
    def test_repeated_publication_reuses_existing_closed_issue(self, gh):
        title, body = render(DATA, PR, "pr:3", PR + "#discussion_r9")
        url = f"https://github.com/{REPO}/issues/5"
        gh.side_effect = [
            "[[]]", url,
            json.dumps([[{"body": body, "html_url": url, "state": "closed", "number": 5}]]),
        ]
        publish(REPO, title, body)
        publish(REPO, title, body)
        creates = [call for call in gh.call_args_list if call.args[:2] == ("issue", "create")]
        self.assertEqual(len(creates), 1)
        self.assertIn("improvement-candidate", creates[0].args)
        self.assertIn(PR + "#discussion_r9", creates[0].kwargs["body"])

    @patch("scripts.feedback.gh")
    def test_local_retry_uses_the_receipt_not_an_issue_list(self, gh):
        title, body = render(DATA, f"https://github.com/{REPO}/issues/2", "local:task-2")
        url = f"https://github.com/{REPO}/issues/5"
        gh.side_effect = ["[[]]", url, json.dumps({"body": body, "html_url": url})]
        with TemporaryDirectory() as scratch:
            publish_local(REPO, 2, title, body, Path(scratch))
            publish_local(REPO, 2, title, body, Path(scratch))
        self.assertEqual(gh.call_args_list[-1].args, ("api", f"repos/{REPO}/issues/5"))
        self.assertEqual(len([c for c in gh.call_args_list if c.args[:2] == ("issue", "create")]), 1)
