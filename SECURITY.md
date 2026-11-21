# Security

## Keys and secrets

- API keys and tokens live **only** in a local `.env` file (ignored by git; copy `.env.example` and fill it in)
  or in the host's secret store (GitHub Actions secrets, Cloudflare secrets). Never in code, commits, logs,
  URLs, test fixtures or command lines.
- `.env` and every `.env.*` file are ignored, except `.env.example`, which holds variable names with empty values.
- Every commit is scanned by gitleaks 8.30.1 (version pinned in `.gitleaks-version`):
  - locally by the pre-commit hook in `.githooks/pre-commit`, which refuses the commit on any finding.
    Enable it once per clone: `git config core.hooksPath .githooks`;
  - over the whole history by `./verify` and by CI on every push.
- On GitHub, turn on secret scanning, push protection and Dependabot alerts for this repository.

## If a key leaks

1. Revoke or rotate the key at the provider at once. Deleting the commit is not enough: assume it was copied.
2. Then remove it from the history and force-push only with the owner's agreement.

## Reporting a problem

Open a private security advisory on the GitHub repository, or write to the maintainer listed there.
