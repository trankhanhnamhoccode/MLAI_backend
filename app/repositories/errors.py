"""Minimal access-layer lifecycle error; database errors retain project convention."""


class InvalidLifecycleTransition(ValueError):
    """A repository writer requires RUNNING, but the run is already terminal."""
