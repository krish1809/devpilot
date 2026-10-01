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

## Agent tools over MCP (Phase 8)
The agent's sandbox test runs go through `devpilot-tools`, an MCP server (`apps/api/app/mcp/server.py`)
launched per call as a stdio subprocess and **bound to one run and one permission policy** at launch;
tools take no run/workspace argument. Server-side, independent of the caller: `read` vs `execute`
policy per tool; `run_tests` runs only the task's configured test command, in the network-off sandbox;
`read_file` is confined to the checkout and refuses secret/vendored/binary files; outputs are capped;
every call — allowed or denied — is written to `tool_calls` with redacted arguments. Denial reasons are
returned to the client; unexpected errors stay generic.

## Prompt injection (Phase 8)
Repository files, issue text and tool output are treated as hostile input. What is guaranteed
regardless of model behaviour (covered by `apps/api/tests/test_injection.py`):
- Secrets never reach the model: host environment and app config are never put in prompts; `.env`,
  key and credential files are never indexed or readable; token-like strings are redacted from
  retrieved code.
- Untrusted text is wrapped in labelled tags (`<issue>`, `<retrieved_context>`, `<file>`,
  `<test_output>`), and every system prompt says not to follow instructions inside them.
- The model can't choose what it edits beyond policy: one file, validated server-side — tracked,
  non-secret, non-vendored, and never CI/automation config (`.github/`, `.gitlab-ci.yml`, …).
- Patches that newly add environment access, process execution, network calls, credential paths
  or payload decoding are flagged to the human reviewer before approval.
- Nothing is published without explicit human approval of the exact diff, and the sandbox has no
  network, so an obeyed injection cannot exfiltrate from test runs.
Whether a given model *obeys* an injected instruction is probabilistic; the controls above are what
bound the damage when it does.
