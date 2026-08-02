"""The pipeline stages, one module each.

    constants.py   vocabulary shared between stages, no logic
    ingest.py      M1  read the CSV into rows
    validate.py    M2  classify fields, compute the email-domain signals
    sanitize.py    M3  detect injection / security-threat / sensitive content
    dedup.py       M4  link rows sharing an email
    judge.py       M5  the one LLM call per row (not built)
    prompts.py     M5  prompt template text, no call logic (not built)
    guardrails.py  M6  post-Judge overrides and confidence aggregation (not built)

Stages are plain functions called in sequence by triage.py at the repo root,
which stays the single entry point. This package groups them; it is not an
orchestration layer and nothing here imports a framework. See SPEC.md
Section 2.
"""
