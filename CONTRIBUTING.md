# Contributing to fastmcp-guard

Thanks for your interest! This is a young project and contributions are very welcome. You are free to use any AI tools during development, however, should be able to explain your changes correctly in the PR.

## Setup

```bash
git clone https://github.com/rohan/fastmcp-guard
cd fastmcp-guard
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

## Code style

```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

## Contribution areas

- New key store backends (DynamoDB, Vault, etc.)
- New audit backends
- Redis distributed rate limiter implementation
- Postgres key store implementation
- Docs improvements
- Additional examples

Open an issue before starting large changes.
