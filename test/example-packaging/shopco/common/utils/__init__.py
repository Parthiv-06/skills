"""Shared utilities package; re-exports the helpers callers should import.
Import from common.utils, not its submodules, so helpers can move freely."""
from common.utils.strings import slugify

__all__ = ["slugify"]
