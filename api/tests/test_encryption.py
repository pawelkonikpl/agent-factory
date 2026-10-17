import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.encryption import EncryptionService


@pytest.fixture
def encryption() -> EncryptionService:
    return EncryptionService(EncryptionService.generate_key())


def test_encrypt_then_decrypt_gives_the_plaintext_back(encryption: EncryptionService) -> None:
    token = encryption.encrypt("tajne hasło")

    assert token != "tajne hasło"
    assert token.startswith("gAAAAA")
    assert encryption.decrypt(token) == "tajne hasło"


def test_invalid_token_is_rejected(encryption: EncryptionService) -> None:
    with pytest.raises(ValueError, match=r"^Decryption failed: ") as error:
        encryption.decrypt("not-a-token")

    assert "not-a-token" not in str(error.value)


def test_empty_text_is_rejected(encryption: EncryptionService) -> None:
    with pytest.raises(ValueError):
        encryption.decrypt("")


def test_token_from_another_key_is_rejected(encryption: EncryptionService) -> None:
    token = EncryptionService(EncryptionService.generate_key()).encrypt("secret")

    with pytest.raises(ValueError, match=r"^Decryption failed: "):
        encryption.decrypt(token)


def test_settings_reject_an_invalid_key_without_printing_it() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(encryption_key="not-a-key")

    message = str(error.value)
    assert "encryption_key" in message
    assert "Fernet" in message
    assert "not-a-key" not in message
