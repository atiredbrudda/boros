# Deferred Items — Phase 02-01

## Pre-existing test failure (out of scope)

**File:** `python/tests/test_screener_filter.py::test_all_six_filters_applied`

**Issue:** Test fixture creates a DuckDB table with `size VARCHAR` but `screener/filter.py`
references `size_float AS size` (snake_case column from Phase 1 fix commit 4f95e62).
The test fixture was not updated when the SQL column name was fixed.

**Evidence:** Failure exists on base commit `d423b01` (pre-Plan-02-01). This plan does
not touch `screener/filter.py` or its test fixtures.

**Resolution:** Phase 01 fix plan or separate test-fixture update needed.
