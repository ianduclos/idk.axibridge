# FROZEN from research commit ecd64f8: tools/gesture/gesture/calligraphy.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""app: the research `calligraphy` module reduced to the one name the kit
library imports. The full module needs PIL and reads the scans; the app only
needs the exception type, so `kit.library.PolicyError` stays a subclass of it
exactly as in the research."""


class PolicyError(RuntimeError):
    """Restricted (measure-only) material reached a generative path."""
