import os
import json
import uuid
import base64
import hashlib
from pathlib import Path
from datetime import datetime

from core.crypto import (
    generate_keypair, private_to_bytes, public_to_bytes,
    bytes_to_private, bytes_to_public, fingerprint,
)


IDENTITY_DIR = Path.home() / ".nocturne"
IDENTITY_FILE = IDENTITY_DIR / "identity.json"


class Identity:
    """
    Идентификация пользователя.
    Хранит: UUID, X25519 ключи, .onion-адрес, отпечаток.
    """

    def __init__(self):
        self.uuid = None
        self.private_key = None
        self.public_key = None
        self.private_bytes = None
        self.public_bytes = None
        self.onion_address = None
        self.fingerprint = None
        self.created = None
        self.nickname = None

    @staticmethod
    def exists():
        return IDENTITY_FILE.exists()

    @staticmethod
    def create(nickname=None):
        """Создаёт новую идентичность."""
        IDENTITY_DIR.mkdir(parents=True, exist_ok=True)

        identity = Identity()
        identity.uuid = str(uuid.uuid4())
        identity.nickname = nickname or "anonymous"

        private, public = generate_keypair()

        identity.private_key = private
        identity.public_key = public
        identity.private_bytes = private_to_bytes(private)
        identity.public_bytes = public_to_bytes(public)
        identity.fingerprint = fingerprint(identity.public_bytes)
        identity.created = datetime.now().isoformat()

        identity.save()

        return identity

    @staticmethod
    def load():
        """Загружает существующую идентичность."""
        if not IDENTITY_FILE.exists():
            return None

        try:
            data = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))

            identity = Identity()
            identity.uuid = data.get("uuid")
            identity.nickname = data.get("nickname", "anonymous")
            identity.private_bytes = base64.b64decode(data["private_key"])
            identity.public_bytes = base64.b64decode(data["public_key"])
            identity.onion_address = data.get("onion_address")
            identity.fingerprint = data.get("fingerprint")
            identity.created = data.get("created")

            identity.private_key = bytes_to_private(identity.private_bytes)
            identity.public_key = bytes_to_public(identity.public_bytes)

            return identity
        except Exception as e:
            return None

    def save(self):
        """Сохраняет идентичность на диск."""
        IDENTITY_DIR.mkdir(parents=True, exist_ok=True)

        try:
            data = {
                "uuid": self.uuid,
                "nickname": self.nickname,
                "private_key": base64.b64encode(self.private_bytes).decode("ascii"),
                "public_key": base64.b64encode(self.public_bytes).decode("ascii"),
                "onion_address": self.onion_address,
                "fingerprint": self.fingerprint,
                "created": self.created,
            }

            IDENTITY_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # защита файла (Unix)
            if os.name != "nt":
                os.chmod(IDENTITY_FILE, 0o600)

            return True
        except Exception:
            return False

    def set_onion(self, onion_address):
        """Устанавливает .onion-адрес (после запуска Tor)."""
        self.onion_address = onion_address
        self.save()

    def get_short_id(self):
        """Короткий ID для отображения."""
        if self.fingerprint:
            return f"{self.fingerprint[:8]}-{self.uuid[:8]}"
        return self.uuid[:16]

    def get_display_name(self):
        if self.nickname and self.nickname != "anonymous":
            return self.nickname
        return self.get_short_id()

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "nickname": self.nickname,
            "fingerprint": self.fingerprint,
            "onion": self.onion_address,
            "short_id": self.get_short_id(),
        }

    @staticmethod
    def delete():
        """Удаляет идентичность (осторожно!)."""
        if IDENTITY_FILE.exists():
            IDENTITY_FILE.unlink()
            return True
        return False

    @staticmethod
    def export_backup(password):
        """Экспорт зашифрованного backup."""
        from core.crypto import encrypt_bytes
        import secrets

        if not IDENTITY_FILE.exists():
            return None, "Нет идентичности"

        data = IDENTITY_FILE.read_bytes()
        encrypted, salt = encrypt_bytes(data, password)

        blob = salt + encrypted
        return base64.b64encode(blob).decode("ascii"), None

    @staticmethod
    def import_backup(b64_data, password):
        """Импорт из backup."""
        from core.crypto import decrypt_bytes
        import secrets

        try:
            blob = base64.b64decode(b64_data)
            salt = blob[:16]
            encrypted = blob[16:]

            data = decrypt_bytes(encrypted, password, salt)
            if data is None:
                return False, "Неверный пароль"

            IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
            IDENTITY_FILE.write_bytes(data)
            return True, None
        except Exception as e:
            return False, str(e)


class Contact:
    """Контакт — другой пользователь."""

    def __init__(self, uuid, public_bytes, onion_address=None,
                 nickname=None, fingerprint=None):
        self.uuid = uuid
        self.public_bytes = public_bytes
        self.public_key = bytes_to_public(public_bytes)
        self.onion_address = onion_address
        self.nickname = nickname or "unknown"
        self.fingerprint = fingerprint or fingerprint(public_bytes)
        self.last_seen = None
        self.online = False

    def to_dict(self):
        return {
            "uuid": self.uuid,
            "public_key": base64.b64encode(self.public_bytes).decode("ascii"),
            "onion_address": self.onion_address,
            "nickname": self.nickname,
            "fingerprint": self.fingerprint,
            "last_seen": self.last_seen,
        }

    @staticmethod
    def from_dict(data):
        return Contact(
            uuid=data["uuid"],
            public_bytes=base64.b64decode(data["public_key"]),
            onion_address=data.get("onion_address"),
            nickname=data.get("nickname"),
            fingerprint=data.get("fingerprint"),
        )

    def get_short_id(self):
        return f"{self.fingerprint[:8]}-{self.uuid[:8]}"

    def get_display_name(self):
        if self.nickname and self.nickname != "unknown":
            return self.nickname
        return self.get_short_id()