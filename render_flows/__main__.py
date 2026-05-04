"""Entry point for ``python -m render_flows``.

This module is intentionally thin — it exists solely to satisfy Python's
``-m`` protocol.  All real CLI logic lives in ``_cli.py`` so that
``__init__.py`` can re-export ``main`` without touching ``__main__``.
"""

# TODO: from render_flows._cli import main
# TODO: if __name__ == "__main__": main()
