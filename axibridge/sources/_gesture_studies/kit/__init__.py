# FROZEN from research commit 6332b35: tools/gesture/gesture/kit/__init__.py
# Written by tools/gesture_studies/freeze.py; do not edit by hand (changes marked "app:").
"""The gesture kit: saved grammars + combinable technique modules.

    from ._research import kit
    sheet = kit.run({"seed": 7000, "voice": {"id": "drift"}})   # recipe → Sheet
    kit.preview(sheet, ".local/gesture/out/kit/x.jpg")           # image + recipe beside it
    kit.list()                                                   # every module + params
    kit.library.entries("hand")                                  # what has been learned

Spec: docs/superpowers/specs/2026-10-17-gesture-kit.md. Adding a technique:
kit/README.md. Every module file in this package is imported on first use,
so a new technique is a new file — no shared file to edit.
"""
from __future__ import annotations

from . import library
from .core import (DEFAULT_CHANNELS, DISCOVERY_ERRORS, KINDS, REQUIRED_CHANNELS, ChannelError, Ctx, Ink, KitError,
                   Mark, P, Param, Part, RecipeError, RegistrationError, Sheet, arranger, channel_kind, contact,
                   describe, discover, fit, fitted, get, modulator, preview, refit, registry, render_image, renderer,
                   run, summary, validate, voice)
from .core import list_modules as list  # noqa: A001 — the spec's name: kit.list()
from .library import PolicyError

__all__ = ["run", "preview", "list", "validate", "describe", "registry", "get", "discover",
           "voice", "modulator", "renderer", "arranger", "P", "Param",
           "Mark", "Ink", "Sheet", "Ctx", "Part", "library", "PolicyError", "RecipeError", "KitError",
           "ChannelError", "RegistrationError", "fit", "fitted", "refit", "channel_kind", "render_image",
           "contact", "summary", "KINDS", "REQUIRED_CHANNELS", "DEFAULT_CHANNELS", "DISCOVERY_ERRORS"]

discover()
