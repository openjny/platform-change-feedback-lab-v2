# Platform Change Feedback Lab

This lab tests whether routine development of a synthetic cloud-platform change
planner can surface improvements to project instructions, standards, or CI.
It runs without an Azure account and does not deploy anything.

## Run the planner

With Python 3.11 or later, from the repository root:

```shell
python -B plan.py profiles/dev.json
python -B -m unittest discover -s tests -v
```

The planner prints `Valid plan` for a valid profile. A rejected profile prints
the field errors and exits with status 2. There are no external packages.
Profile filenames can describe their role. The `environment` field uses
`dev`, `tst`, or `prd`; the [preproduction example](profiles/preprod.json)
uses `tst`. CI validates every JSON profile in `profiles/`.

## Try the feedback loop

Follow [the experiment procedure](docs/experiment.md) to work from an issue,
reflect in Copilot, and merge a reviewed pull request. The output is a GitHub
issue with the `improvement-candidate` label, not a change to the project rules.
The [compatibility notes](docs/compatibility.md) distinguish Visual Studio
documentation from the behavior we can verify in Copilot CLI.

See [contributing](CONTRIBUTING.md) and [repository terms](LICENSE) before
submitting material. This public repository accepts synthetic data only.
