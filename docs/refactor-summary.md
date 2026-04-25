# Python Refactor Summary

Scope: all project Python files under `backend`, `frontend`, `monitoring`, `research`, `scripts`, `crypto-history`, and `SP500`, excluding virtual environments and cache/backups.

## Files that need refactoring

| Priority | File | Lines | Rule triggered | Recommendation |
|---|---:|---:|---|---|
| Immediate | `backend/app/api/routers/ml.py` | 1711 | 1000+ lines: refactor before continuing | Split into smaller modules now; this file is far beyond the maintainable limit. |
| High | `backend/app/ml/training_inputs.py` | 643 | 600+ lines: should not exceed 600 without a reason | Refactor or split to keep the module under the guideline threshold. |

## Threshold notes

- No files were found in the 800-999 line range.
- The project has one file above 1000 lines and one file above 600 lines.
- Any future Python feature work should avoid growing these files further without a planned split.

## Suggested next steps

1. Break `backend/app/api/routers/ml.py` into smaller router/service modules.
2. Review `backend/app/ml/training_inputs.py` and split by responsibility.
3. Re-run the line-count check after the refactor to confirm both files are below the target thresholds.
