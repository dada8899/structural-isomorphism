"""Root contracts keep pytest capture, without its non-application null file sink."""
from contextlib import contextmanager
import logging
import os

import pytest


@contextmanager
def _without_pytest_null_file(config):
    # Pytest attaches this discard-only FileHandler for the whole run even
    # when --log-file was not requested. It is test infrastructure, whereas
    # actual Main deliberately rejects every application disk FileHandler.
    plugin=config.pluginmanager.get_plugin("logging-plugin")
    handler=getattr(plugin,"log_file_handler",None)
    root=logging.getLogger()
    owned_null=(isinstance(handler,logging.FileHandler)
                and handler.baseFilename==os.path.abspath(os.devnull)
                and handler in root.handlers)
    if owned_null:
        root.removeHandler(handler)
    try:
        yield
    finally:
        if owned_null and handler not in root.handlers:
            root.addHandler(handler)


@pytest.hookimpl(wrapper=True,trylast=True)
def pytest_runtestloop(session):
    # Run inside pytest's logging wrapper. caplog, report capture, stream
    # handlers and every real file handler remain installed and tested.
    with _without_pytest_null_file(session.config):
        return (yield)
