"""parrhesia: held-out geometric evaluation for whole-scroll surface fits."""

from importlib.metadata import PackageNotFoundError, version

try:  # single source of truth: the installed package metadata
    __version__ = version("parrhesia")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"
