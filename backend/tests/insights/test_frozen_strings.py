"""Every frozen Part F string passes the F2/F3 boundary checks."""
from app.insights.strings import STRINGS, check_boundaries


def test_every_frozen_string_passes_boundary_checks():
    failures = {}
    for key, template in STRINGS.items():
        f = check_boundaries(template, key=key)
        if f:
            failures[key] = f
    assert not failures, failures
