# DevPilot — Security Design

Security is central because the eventual platform reads repositories and may execute AI-generated code.

## Trust boundaries
Treat task text, GitHub issue/comment content, repository files, model output, tool output, build scripts, and test logs as untrusted. Repository prompt injection must not alter tool permissions or system policy.

## Identity and secrets
- Authenticate users before accessing private resources.
- Enforce project/repository ownership server-side.
- Use least-privilege GitHub permissions and short-lived tokens where possible.
- Keep credentials server-side; use secret management in hosted environments.
- Ignore `.env`; commit only placeholder values in `.env.example`.
- Never put keys in prompts, frontend bundles, logs, traces, or artifacts.

## Tool permissions
Each tool needs a typed schema, explicit permission, server-side authorization, timeout, output limit, and audit record. Model output cannot authorize itself. Apply rate limits and narrow scopes.

## Sandbox
Before running repository code, use a disposable isolated environment with CPU, memory, process, disk, and time limits. Disable network by default. Mount only required workspace data. DevPilot runs the container as the host's non-root uid with bytecode writes off, so nothing it writes into the checkout is root-owned. Never mount the host Docker socket or pass host credentials into untrusted code. Bound logs and clean up reliably. Docker alone may not be a sufficient boundary for every multi-tenant threat model; review before hosted arbitrary-code execution.

## Human approval
Require explicit approval before publishing a branch/PR. Bind approval to the exact diff/artifact hash and base commit; invalidate it if the artifact changes. Record approver, decision, and timestamp.

## Data protection
Repository indexing (Phase 6) only reads git-tracked text files at the pinned commit; it skips vendored/generated directories, lockfiles, minified assets, binaries, files over 200 KB, key/credential files (`.env*`, `*.pem`, `id_rsa*`, …) and any file containing a private key, and redacts token-like strings (GitHub/AWS/OpenAI/Groq/Slack/Google keys, `password = "…"`) before chunks are embedded or shown to the model. A model-chosen target file must pass the same policy.
Minimize retained source and logs. Scope retrieval by user/repository/commit. Define retention/deletion. Avoid logging full source, prompts, or diffs by default. Prevent cross-user retrieval.

## Production checklist
Auth/RBAC, TLS/CORS, secret management, rate and size limits, verified webhook signatures, sandbox isolation, dependency/container scanning, safe errors, backups and restore testing, approval-gate tests, and telemetry redaction.
