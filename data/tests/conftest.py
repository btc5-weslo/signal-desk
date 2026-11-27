"""Shared fixtures. Importing tests does not hit the network or write the store."""

from tests.toy import make_bars  # re-export for fixtures / convenience

__all__ = ["make_bars"]
