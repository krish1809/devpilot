# SWE-bench Lite — DevPilot (lite-s20-seed7)

Seeded random sample of **20** of the 300 SWE-bench Lite test instances (seed 7); **20 attempted so far**. LLM `openai/gpt-oss-120b` (Groq free tier), embeddings `BAAI/bge-small-en-v1.5`. Patches scored with the **official SWE-bench harness** (`swebench.harness.run_evaluation`): an instance is resolved only if all FAIL_TO_PASS and PASS_TO_PASS tests pass.

The agent never sees the benchmark's tests (standard setting): it gets the issue text, retrieves/plans/edits one file, and the automated reviewer gates the diff.

| Config | Resolved | Resolve rate (95% CI) | Patch produced | Edited gold file | Avg LLM calls | Avg tokens | Avg time |
|---|---|---|---|---|---|---|---|
| **RAG, issue only** (realistic) | 0/1 | 0% (0%–79%) | 12/20 | 11/20 | 1.8 | 5,776 | 47s |
| Oracle file, no retrieval | 0/1 | 0% (0%–79%) | 12/20 | 20/20 | 1.7 | 4,354 | 22s |
| Oracle file + RAG context | 0/0 | not scored | 11/20 | 20/20 | 1.6 | 5,748 | 25s |
| Reference (gold) patch — environment ceiling | 1/1 | 100% (21%–100%) | 1/1 | 1/1 | 0.0 | 0 | 0s |

Scored by: GitHub Actions https://github.com/krish1809/devpilot/actions/runs/39701119345.

| Instance | rag | oracle-file | oracle-file+rag | gold |
|---|---|---|---|---|
| django__django-11620 | ❌ validated | ❌ validated | · validated | ✅ reference |
| django__django-11848 | · validated | · validated | · validated | — |
| django__django-12113 | · validated | · validated | · validated | — |
| django__django-12453 | · validated | · validated | · validated | — |
| django__django-12497 | · error | · validated | · error | — |
| django__django-12915 | · validated | · validated | · validated | — |
| django__django-13028 | · validated | · validated | · validated | — |
| django__django-13158 | · error | · error | · error | — |
| django__django-14672 | · error | · validated | · validated | — |
| django__django-16379 | · validated | · validated | · validated | — |
| matplotlib__matplotlib-23299 | · validated | · error | · error | — |
| pylint-dev__pylint-7228 | · error | · error | · error | — |
| scikit-learn__scikit-learn-11040 | · validated | · error | · validated | — |
| scikit-learn__scikit-learn-15535 | · validated | · validated | · validated | — |
| sphinx-doc__sphinx-8282 | · error | · error | · error | — |
| sphinx-doc__sphinx-8801 | · error | · error | · error | — |
| sympy__sympy-16988 | · validated | · validated | · validated | — |
| sympy__sympy-19487 | · validated | · validated | · error | — |
| sympy__sympy-21055 | · error | · error | · error | — |
| sympy__sympy-24213 | · error | · error | · error | — |

Legend: ✅ resolved · ❌ not resolved · · not scored yet · — not run. Status is the agent's final state (`validated` = a patch passed review; `review_failed`/`error` = no patch submitted).
