# Development

```sh
uv venv --python 3.14 && uv pip install -r requirements-test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest
```

The tests run the integration inside Home Assistant against a local stand-in for the xAI API (`tests/conftest.py`).

## Live tests

`tests/test_live.py` runs the same entities against the real API and prints latencies. It is skipped unless `XAI_API_KEY` is set in the environment or in a `.env` file at the repository root. It costs a fraction of a cent per run:

```sh
.venv/bin/python -m pytest tests/test_live.py -s
```

## CI and releases

- The Test workflow runs ruff and pytest on pushes to `master` and on pull requests.
- The Validate workflow runs hassfest and the Marketplace repository checks.
- The Image pins workflow checks, weekly, the hassfest and HACS images the Validate workflow runs by digest against their tags, and opens a pull request moving any that moved.
- The Issue to PR workflow has Claude turn an issue opened by the owner, one labelled `claude`, or one the owner (or a collaborator) comments `@claude` on, into a pull request. Before it works, `.github/actions/setup` installs what the Test workflow does (Python 3.14 and `requirements-test.txt`), and it may run only ruff and pytest; change those with the Test workflow.
- The Claude workflow answers `@claude` in a pull request's comment or review, there or by changing its branch. It may run the same commands as Issue to PR.
- The Release pull request workflow keeps one pull request, `Release v<version>`, open on `master` with the next version in `custom_components/xai_grok/manifest.json`: major for a breaking change (`type!:`), minor for a `feat`, patch for anything else that changes `custom_components/`. To release, merge it: the Release workflow then runs after Test passes and creates the GitHub release `v<version>` with generated notes. Don't bump the version by hand.
