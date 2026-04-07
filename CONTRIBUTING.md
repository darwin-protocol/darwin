# Contributing to DARWIN

## Start

```bash
./ops/bootstrap_dev.sh
source .venv/bin/activate
cd sim && python -m pytest tests/test_end_to_end.py -v
cd ../contracts && forge test --summary
```

## Expectations

- keep changes focused
- include tests when behavior changes
- avoid committing generated artifacts or local environment data
- avoid publishing private operational detail in public-facing docs

## Scope

Useful public contributions include:

- simulator improvements
- contract fixes and tests
- public site and wallet UX
- documentation improvements for public users
