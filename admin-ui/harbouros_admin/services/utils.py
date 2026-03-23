"""Shared utilities for HarbourOS service modules."""

import os


def _sudo(cmd):
    """Prepend sudo to a command when running as non-root."""
    if os.getuid() != 0 and not os.environ.get("HARBOUROS_DEV"):
        return ["sudo"] + cmd
    return cmd
