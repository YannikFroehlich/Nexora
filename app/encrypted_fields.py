import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

ENCRYPTED_VALUE_PREFIX = "fernet$"


def _encryption_key():
    configured_key = (
        settings.NEXORA_OAUTH_TOKEN_ENCRYPTION_KEY.strip()
        or settings.SPOTIFY_TOKEN_ENCRYPTION_KEY.strip()
    )

    if configured_key:
        try:
            return configured_key.encode("ascii")
        except UnicodeEncodeError as error:
            raise ImproperlyConfigured(
                "NEXORA_OAUTH_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
            ) from error

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=4)
def _fernet(key):
    try:
        return Fernet(key)
    except (TypeError, ValueError) as error:
        raise ImproperlyConfigured(
            "NEXORA_OAUTH_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from error


class EncryptedTextField(models.TextField):
    """Text field that encrypts values before they reach the database."""

    def from_db_value(self, value, expression, connection):
        return self._decrypt(value)

    def to_python(self, value):
        value = super().to_python(value)
        return self._decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)

        if not value or value.startswith(ENCRYPTED_VALUE_PREFIX):
            return value

        encrypted_value = _fernet(_encryption_key()).encrypt(value.encode("utf-8"))
        return f"{ENCRYPTED_VALUE_PREFIX}{encrypted_value.decode('ascii')}"

    @staticmethod
    def _decrypt(value):
        if not value or not value.startswith(ENCRYPTED_VALUE_PREFIX):
            return value

        encrypted_value = value.removeprefix(ENCRYPTED_VALUE_PREFIX)

        try:
            return (
                _fernet(_encryption_key()).decrypt(encrypted_value.encode("ascii")).decode("utf-8")
            )
        except (InvalidToken, UnicodeDecodeError, ValueError) as error:
            raise ImproperlyConfigured(
                "An OAuth token could not be decrypted. Check the token encryption key."
            ) from error
