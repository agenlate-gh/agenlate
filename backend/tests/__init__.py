"""Backend test suite.

This package marker exists so test modules get fully qualified names. Without
it, two files sharing a basename in different directories — tests/test_billing.py
and tests/integration/test_billing.py — collide at collection.
"""
