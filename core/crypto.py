import os
import base64
import json
import hashlib
import secrets
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization


def generate_keypair():
    """Генерирует X25519 пару ключей."""
    private = X25519PrivateKey.generate()
    public = private.public_key()
    return private, public


def private_to_bytes(private_key):
    """Сериализует приватный ключ в bytes."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def public_to_bytes(public_key):
    """Сериализует публичный ключ в bytes."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def bytes_to_private(data):
    return X25519PrivateKey.from_private_bytes(data)


def bytes_to_public(data):
    return X25519PublicKey.from_public_bytes(data)


def derive_shared_key(private_key, peer_public_key):
    """
    Diffie-Hellman: получает общий секрет и превращает в AES-ключ.
    """
    shared = private_key.exchange(peer_public_key)

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"nocturne-e2ee-v1",
    )
    return hkdf.derive(shared)


def encrypt_message(shared_key, plaintext):
    """AES-256-GCM. Возвращает base64-строку."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")

    aes = AESGCM(shared_key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, plaintext, None)

    blob = nonce + ct
    return base64.b64encode(blob).decode("ascii")


def decrypt_message(shared_key, b64_data):
    """Расшифровывает AES-256-GCM."""
    try:
        aes = AESGCM(shared_key)
        blob = base64.b64decode(b64_data)
        nonce = blob[:12]
        ct = blob[12:]
        return aes.decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return None


def encrypt_bytes(shared_key, data):
    """AES-GCM для бинарных данных."""
    if isinstance(data, str):
        data = data.encode("utf-8")

    aes = AESGCM(shared_key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, data, None)

    return nonce + ct


def decrypt_bytes(shared_key, blob):
    try:
        aes = AESGCM(shared_key)
        nonce = blob[:12]
        ct = blob[12:]
        return aes.decrypt(nonce, ct, None)
    except Exception:
        return None


def fingerprint(public_key_bytes):
    """Короткий отпечаток ключа для отображения."""
    h = hashlib.sha256(public_key_bytes).hexdigest()
    return h[:16].upper()


def verify_fingerprint(public_key_bytes, expected):
    """Проверяет, что отпечаток совпадает."""
    return fingerprint(public_key_bytes) == expected.upper()