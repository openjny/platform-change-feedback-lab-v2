import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LABEL = "improvement-candidate"
CATEGORIES = {"docs", "instructions", "standard", "lint-ci"}
REPO = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+")
TEXT_FIELDS = {"title": 95, "finding": 500, "suggestion": 500}
COPILOT_REVIEWER = "copilot-pull-request-reviewer[bot]"
PROPOSAL_FENCE = re.compile(r"^```platform-feedback[ \t]*\r?\n(.+?)^```[ \t]*\r?$", re.M | re.S)
PROFILE_FILE = re.compile(r"profiles/[a-z][a-z0-9-]*\.json")


def repository(value):
    if not REPO.fullmatch(value):
        raise ValueError("Repository must be a github.com OWNER/REPO.")
    return value


def number(value):
    if type(value) is not int or value < 1:
        raise ValueError("Expected a positive GitHub item number.")
    return value


def candidate(value):
    if not isinstance(value, dict) or set(value) != {"category", *TEXT_FIELDS}:
        raise ValueError("Candidate fields do not match the schema.")
    if not isinstance(value["category"], str) or value["category"] not in CATEGORIES:
        raise ValueError("Unknown improvement category.")
    for key, limit in TEXT_FIELDS.items():
        text = value[key]
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise ValueError(f"{key} must be a nonempty string of at most {limit} characters.")
        if not text.isprintable() or re.search(r"[<>\[\]@#`]|https?:", text, re.I):
            raise ValueError(f"{key} must be plain text without mentions, references, or links.")
    return value


def gh(*args, body=None):
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat"}
    return subprocess.run(
        ["gh", *args], input=body, capture_output=True, check=True, encoding="utf-8", env=env,
    ).stdout.strip()


def api(path):
    return json.loads(gh("api", path))


def evidence_url(url, repo, pr):
    root = re.escape(f"https://github.com/{repo}")
    if not isinstance(url, str) or not re.fullmatch(
        rf"{root}/(?:pull/{pr}(?:#(?:discussion_r|pullrequestreview-|issuecomment-)[0-9]+)?"
        r"|actions/runs/[0-9]+(?:/job/[0-9]+)?|runs/[0-9]+)", url,
    ):
        raise ValueError("Evidence URL must belong to the source repository and PR or check.")
    return url


def render(proposal, source, marker, evidence=None):
    body = [
        f"<!-- platform-feedback:{marker} -->",
        f"Source: {source}",
        f"Category: `{proposal['category']}`",
    ]
    if evidence is not None:
        body.append(f"Evidence: {evidence}")
    body.extend([
        "", "## Observed friction", "", proposal["finding"],
        "", "## Suggested project change", "", proposal["suggestion"],
        "", "Pending human triage. No project rules were changed.",
    ])
    return proposal["title"], "\n".join(body)


def publish(repo, title, body):
    marker = body.splitlines()[0]
    pages = json.loads(gh(
        "api", "--paginate", "--slurp",
        f"repos/{repo}/issues?state=all&labels={LABEL}&per_page=100",
    ))
    for page in pages:
        for issue in page:
            if "pull_request" not in issue and marker in (issue["body"] or "").splitlines():
                print(f"Already recorded: {issue['html_url']}")
                return
    url = gh("issue", "create", "--repo", repo, "--title", title, "--label", LABEL,
             "--body-file", "-", body=body)
    print(f"Created: {url}")


def local_command(args):
    repo = repository(args.repo)
    data = json.loads(args.draft.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"work_item", "candidate"}:
        raise ValueError("Draft must contain exactly work_item and candidate.")
    task = number(data["work_item"])
    title, body = render(candidate(data["candidate"]), f"https://github.com/{repo}/issues/{task}",
                         f"local:task-{task}")
    if args.command == "preview":
        print(f"{title}\n\n{body}")
        return
    origin = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, check=True, encoding="utf-8",
    ).stdout.strip()
    origins = {f"{prefix}{repo}{suffix}".lower()
               for prefix in ("https://github.com/", "git@github.com:")
               for suffix in ("", ".git")}
    if origin.lower() not in origins:
        raise ValueError("The explicit repository does not match this checkout's GitHub origin.")
    if "pull_request" in api(f"repos/{repo}/issues/{task}"):
        raise ValueError("The local draft must cite a work issue, not a pull request.")
    publish(repo, title, body)


def event_pr(event, repo):
    pr = event["pull_request"]
    if (event["action"] != "closed" or not pr["merged"] or pr["base"]["ref"] != "main"
            or pr["head"]["repo"]["full_name"] != repo
            or event["sender"]["login"] != repo.split("/")[0]):
        raise ValueError("Only owner merges of same-repository PRs to main are eligible.")
    return pr


def classify(evidence, files, ci, owner):
    for item in evidence:
        supported_review = item["kind"] in {"review", "inline"} and item["author"] in {
            owner, COPILOT_REVIEWER,
        }
        if supported_review and (block := PROPOSAL_FENCE.search(item["text"])):
            try:
                proposal = candidate(json.loads(block[1]))
            except ValueError as error:
                print(f"Skipped invalid structured review at {item['url']}: {error}")
                continue
            return {"candidate": proposal, "evidence": item["url"], "method": "structured review"}

    new_profiles = [
        item["filename"] for item in files
        if item["status"] == "added" and PROFILE_FILE.fullmatch(item["filename"])
    ]
    profile_checks = re.findall(r"^\s*-\s+run:\s+python -B plan\.py (.+)$", ci, re.M)
    if not new_profiles or profile_checks != ["profiles/dev.json"]:
        return None
    for item in evidence:
        if (item["kind"] in {"review", "inline"}
                and item["author"] in {owner, COPILOT_REVIEWER}
                and re.search(r"\bCI\b", item["text"], re.I)
                and "profiles/dev.json" in item["text"]):
            return {
                "candidate": {
                    "category": "lint-ci",
                    "title": "Validate every committed profile in Planner CI",
                    "finding": "A new checked-in profile is outside the Planner CI smoke command, which validates only the development example.",
                    "suggestion": "Validate every JSON profile in CI and confirm that adding an invalid profile makes the check fail.",
                },
                "evidence": item["url"],
                "method": "verified planner CI coverage rule",
            }
    return None


def collect(repo, pr):
    n = number(pr["number"])
    endpoint = f"repos/{repo}/pulls/{n}"
    evidence = []
    for kind, route in (("review", f"{endpoint}/reviews"), ("inline", f"{endpoint}/comments")):
        for item in api(f"{route}?per_page=25"):
            if item.get("state") != "DISMISSED" and (item.get("body") or "").strip():
                evidence.append({
                    "kind": kind,
                    "author": (item.get("user") or {}).get("login"),
                    "url": evidence_url(item["html_url"], repo, n),
                    "text": item["body"][:4000],
                })
    checks = api(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs?per_page=30")
    files = api(f"{endpoint}/files?per_page=20")
    print(f"Read {len(evidence)} reviews/comments, {len(checks['check_runs'])} checks, "
          f"and {len(files)} changed files.", flush=True)
    return evidence, files


def workflow(command):
    repo = repository(os.environ["GITHUB_REPOSITORY"])
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    pr = event_pr(event, repo)
    n = number(pr["number"])
    if command == "analyze-pr":
        evidence, files = collect(repo, pr)
        ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        decision = classify(evidence, files, ci, repo.split("/")[0])
        if decision is None:
            print("No valid structured proposal or matching profile coverage gap.")
            return
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write("proposal=" + json.dumps(decision) + "\n")
        print(f"Selected one proposal via {decision['method']}.")
        return
    proposal = json.loads(os.environ["PROPOSAL"])
    evidence = evidence_url(proposal["evidence"], repo, n)
    source = f"https://github.com/{repo}/pull/{n}"
    title, body = render(candidate(proposal["candidate"]), source, f"pr:{n}", evidence)
    publish(repo, title, body)


def main():
    parser = argparse.ArgumentParser(description="Review and publish project feedback.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "publish"):
        local = commands.add_parser(command)
        local.add_argument("draft", type=Path)
        local.add_argument("--repo", required=True)
    for command in ("analyze-pr", "publish-pr"):
        commands.add_parser(command)
    args = parser.parse_args()
    try:
        if args.command in {"preview", "publish"}:
            local_command(args)
        else:
            workflow(args.command)
    except subprocess.CalledProcessError as error:
        print(f"Feedback command failed (exit {error.returncode}): {error.stderr}", file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        print(f"Feedback failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
