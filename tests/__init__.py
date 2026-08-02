"""Makes tests/ an importable package, which unittest discovery requires.

Not optional and not cosmetic. Verified on Python 3.11.4, 2026-08-01: without
this file, `python3 -m unittest discover -p "test_*.py"` from the repo root
reports `Ran 0 tests ... OK` and exits 0. The documented command would pass
while running nothing, which looks identical to success. `-s tests -t .` does
not help either; it raises `ImportError: Start directory is not importable`.

Deleting this file therefore silently disables the entire suite.
"""
