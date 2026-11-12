"""Delay the unchanged JWT library until a request actually uses it.

Formal startup verifies the cryptographic dependency files before importing
them. PyJWT imports optional crypto backends eagerly, even for HMAC tokens.
"""
from importlib import import_module


class _DeferredJwt:
    __slots__ = ()

    def __getattr__(self, name):
        if name not in ('encode', 'decode', 'PyJWTError'):
            raise AttributeError(name)
        return getattr(import_module('jwt'), name)


jwt = _DeferredJwt()
