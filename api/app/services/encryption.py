"""Symmetric encryption of stored secrets (SMTP passwords) with Fernet."""

from cryptography.fernet import Fernet, InvalidToken


class EncryptionService:
    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        # The Fernet token is already URL-safe base64: store it as is.
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token:
            raise ValueError("Cannot decrypt empty text")
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            # Neither the token nor the key goes into the message.
            raise ValueError("Decryption failed: invalid token") from None

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()
