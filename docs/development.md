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
- The Release workflow runs after Test passes on a push to `master`. If the `version` in `custom_components/xai_grok/manifest.json` has no release yet, it creates the GitHub release `v<version>` with generated notes. To release, bump the version and push.
