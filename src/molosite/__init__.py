"""molosite: keeps the molonari.io WordPress site in step with the CGS-MOLO branch of MOLONARI1D."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("molosite")
except PackageNotFoundError:  # not installed: running from a bare checkout
    __version__ = "0+unknown"
