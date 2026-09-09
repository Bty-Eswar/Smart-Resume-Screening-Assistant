# conftest.py — Determinism Charter D7 Network Guard
import socket
import pytest


class NetworkForbiddenError(RuntimeError):
    """Raised when any code under test attempts to open a network socket (D7)."""
    pass


_original_connect = socket.socket.connect
_original_create_connection = socket.create_connection


def _forbidden_connect(self, address, *args, **kwargs):
    raise NetworkForbiddenError(
        f"Network connection to {address} forbidden during test execution (Charter D7)"
    )


def _forbidden_create_connection(address, *args, **kwargs):
    raise NetworkForbiddenError(
        f"Network connection to {address} forbidden during test execution (Charter D7)"
    )


# Active across all pytest runs
socket.socket.connect = _forbidden_connect
socket.create_connection = _forbidden_create_connection
