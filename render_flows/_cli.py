"""Command-line interface for render_flows.

``main()`` lives here rather than in ``__main__.py`` so that it can be
imported and re-exported by ``__init__.py`` without the risks that arise
when a package's ``__init__`` imports from its own ``__main__`` module
(Python's import machinery treats ``__main__`` specially when a package is
invoked with ``python -m``).

``__main__.py`` is a three-line wrapper that calls ``main()`` from here.
"""

# TODO: move main() from homey_flow_svg.py
