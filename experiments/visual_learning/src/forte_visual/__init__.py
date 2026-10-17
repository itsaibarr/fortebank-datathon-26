"""Shared lightweight scanner; optional experiment tools live in their own wheel."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
