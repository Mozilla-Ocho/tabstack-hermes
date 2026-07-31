"""Directory-install shim.

Hermes loads a directory plugin by importing the ``__init__.py`` that sits next
to ``plugin.yaml`` (as ``hermes_plugins.<slug>``, with the plugin directory on
the module's ``__path__``). When this repository is cloned straight into
``~/.hermes/plugins/`` that root file is this one, so it re-exports ``register``
from the real package below it.

The pip install path does not use this file: the ``hermes_agent.plugins`` entry
point points at the ``tabstack_hermes`` package directly, and only that package
is included in the wheel.
"""

from __future__ import annotations

from .tabstack_hermes import register

__all__ = ["register"]
