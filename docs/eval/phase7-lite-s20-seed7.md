# SWE-bench Lite — DevPilot (lite-s20-seed7)

Seeded random sample of **20** of the 300 SWE-bench Lite test instances (seed 7), LLM `openai/gpt-oss-120b` (Groq free tier), embeddings `BAAI/bge-small-en-v1.5`. Patches scored with the **official SWE-bench harness** (`swebench.harness.run_evaluation`): an instance is resolved only if all FAIL_TO_PASS and PASS_TO_PASS tests pass.

The agent never sees the benchmark's tests (standard setting): it gets the issue text, retrieves/plans/edits one file, and the automated reviewer gates the diff.

| Config | Resolved | Resolve rate (95% CI) | Patch produced | Edited gold file | Avg LLM calls | Avg tokens | Avg time |
|---|---|---|---|---|---|---|---|
| **RAG, issue only** (realistic) | 0/1 | 0% (0%–79%) | 1/1 | 0/1 | 2.0 | 5,482 | 6s |
| Oracle file, no retrieval | 0/1 | 0% (0%–79%) | 1/1 | 1/1 | 2.0 | 4,656 | 6s |
| Oracle file + RAG context | 0/0 | not scored | 0/0 | 0/0 | 0.0 | 0 | 0s |
| Reference (gold) patch — environment ceiling | 1/1 | 100% (21%–100%) | 1/1 | 1/1 | 0.0 | 0 | 0s |

| Instance | rag | oracle-file | oracle-file+rag | gold |
|---|---|---|---|---|
| django__django-11620 | ❌ validated | ❌ validated | — | ✅ reference |
| django__django-11848 | — | — | — | — |
| django__django-12113 | — | — | — | — |
| django__django-12453 | — | — | — | — |
| django__django-12497 | — | — | — | — |
| django__django-12915 | — | — | — | — |
| django__django-13028 | — | — | — | — |
| django__django-13158 | — | — | — | — |
| django__django-14672 | — | — | — | — |
| django__django-16379 | — | — | — | — |
| matplotlib__matplotlib-23299 | — | — | — | — |
| pylint-dev__pylint-7228 | — | — | — | — |
| scikit-learn__scikit-learn-11040 | — | — | — | — |
| scikit-learn__scikit-learn-15535 | — | — | — | — |
| sphinx-doc__sphinx-8282 | — | — | — | — |
| sphinx-doc__sphinx-8801 | — | — | — | — |
| sympy__sympy-16988 | — | — | — | — |
| sympy__sympy-19487 | — | — | — | — |
| sympy__sympy-21055 | — | — | — | — |
| sympy__sympy-24213 | — | — | — | — |

Legend: ✅ resolved · ❌ not resolved · · not scored yet · — not run. Status is the agent's final state (`validated` = a patch passed review; `review_failed`/`error` = no patch submitted).
