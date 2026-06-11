"""Effect modules: per-layer, non-destructive, paper-space geometry shaping.

Drop a new ``.py`` file here with a ``@register_effect`` class and it appears
in every layer's effect stack on next start. Effects receive geometry already
placed on the paper (the layer transform is applied first), so parameters in
mm mean mm on the final sheet. See docs/MODULES.md.
"""
