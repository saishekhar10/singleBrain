"""Vocabulary shared between stages, and nothing else.

These words are produced by one stage and read back by another: SPEC.md
Section 6 has M6 reading Validate's field statuses and Sanitize's content
categories off their output. Keeping them here means Guardrails never has to
import from Validate's or Sanitize's module just to borrow a string, which
would couple stages that are meant to be independent.

No logic lives here. Anything that does belongs to a stage.
"""

# SPEC.md Section 6's vocabulary note: three terms for field problems, plus OK.
# M6 reads these same words back off Validate's output, so they are defined
# once here rather than restated per stage.
OK = "ok"
MISSING = "missing"
MALFORMED = "malformed"
UNPARSEABLE = "unparseable"

# SPEC.md Section 1's content_flags categories, matching Section 6's trust_risk
# names exactly. Priority among them lives in M6's trust_risk formula and
# nowhere in this stage: here all three are checked independently and every one
# that fires is recorded, because SPEC.md Section 1 says content_flags records
# everything Sanitize found, not just the one driving the score.
INJECTION = "injection"
SECURITY_THREAT = "security_threat"
SENSITIVE_CONTENT = "sensitive_content"

CONTENT_CATEGORIES = (INJECTION, SECURITY_THREAT, SENSITIVE_CONTENT)
