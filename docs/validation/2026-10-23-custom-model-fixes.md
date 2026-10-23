# Preserve deployed custom-model fixes

Imported the two existing Claude fixes from the original dirty checkout into `feature/optimize-261022`:

1. Custom endpoint model discovery reuses a saved key on the same endpoint when the form key is blank/masked. A newly typed key takes precedence; a different endpoint does not receive that key.
2. Renaming the active custom LLM or vision model moves its active selector to the new ID and preserves the saved key. Active embedding/OCR/rerank renames remain blocked.

The entire `app/routers/admin_custom_models.py` module now matches both the original checkout and the running API module (normalized UTF-8 text SHA256):

`3abe4f47f37bce8e113d3b6102d5e1d72907692837367b86ab7ecc28de615cf9`

The API checked was `cahy-wiki-backend:upload-scope-261023-cb617a4`, which preserves the earlier r8 runtime fixes. No API/worker restart or live model setting change was needed for this preservation.

Regression verification: before importing the fixes, five new cases failed for missing saved-key reuse and 409 on active LLM/vision renames. After import, `python -m pytest -q tests/test_custom_models.py` reports **23 passed**. Configuration is isolated in memory; no live keys or model selections were changed.

Other dirty files in the original checkout were not staged, reset or overwritten. This commit preserves the fixes on the feature branch; the original checkout's uncommitted changes remain there.
