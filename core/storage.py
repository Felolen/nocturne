import os
import json
import base64
import sqlite3
from pathlib import Path
from datetime import datetime

from core.crypto import encrypt_bytes, decrypt_bytes


STORAGE_DIR = Path.home() / ".nocturne"
MESSAGES_DB = STORAGE_DIR / "messages.db"
CONTACTS_FILE = STORAGE_DIR / "contacts.json"
SETTINGS_FILE = STORAGE_DIR / "settings.json"


class MessageStore:
    """
    Хранилище сообщений.
    Сообщения хранятся в SQLite в зашифрованном виде.
    """

    def __init__(self, encryption_key=None):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.encryption_key = encryption_key
        self._init_db()

    def _init_db(self):
        con = sqlite3.connect(MESSAGES_DB)
        con.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                msg_id TEXT UNIQUE,
                contact_uuid TEXT NOT NULL,
                direction TEXT NOT NULL,
                encrypted_data TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                delivered INTEGER DEFAULT 0,
                read INTEGER DEFAULT 0
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_contact
            ON messages(contact_uuid, timestamp)
        """)
        con.commit()
        con.close()

    def add_message(self, msg_id, contact_uuid, direction,
                    plaintext, timestamp=None):
        """Добавляет сообщение. Если есть ключ — шифрует."""
        if self.encryption_key:
            encrypted = encrypt_bytes(self.encryption_key, plaintext)
            encrypted_b64 = base64.b64encode(encrypted).decode("ascii")
        else:
            encrypted_b64 = base64.b64encode(
                plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
            ).decode("ascii")

        ts = timestamp or datetime.now().isoformat()

        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("""
                INSERT OR REPLACE INTO messages
                (msg_id, contact_uuid, direction, encrypted_data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (msg_id, contact_uuid, direction, encrypted_b64, ts))
            con.commit()
            return True
        except Exception:
            return False
        finally:
            con.close()

    def get_messages(self, contact_uuid, limit=100):
        """Возвращает сообщения контакта."""
        con = sqlite3.connect(MESSAGES_DB)
        try:
            rows = con.execute("""
                SELECT msg_id, direction, encrypted_data, timestamp
                FROM messages
                WHERE contact_uuid = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (contact_uuid, limit)).fetchall()
        finally:
            con.close()

        result = []
        for msg_id, direction, encrypted_b64, ts in rows:
            try:
                blob = base64.b64decode(encrypted_b64)

                if self.encryption_key:
                    plaintext = decrypt_bytes(self.encryption_key, blob)
                    if plaintext:
                        text = plaintext.decode("utf-8")
                    else:
                        text = "[не удалось расшифровать]"
                else:
                    text = blob.decode("utf-8")

                result.append({
                    "id": msg_id,
                    "direction": direction,
                    "text": text,
                    "timestamp": ts,
                })
            except Exception:
                continue

        return result

    def delete_message(self, msg_id):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("DELETE FROM messages WHERE msg_id = ?", (msg_id,))
            con.commit()
            return True
        finally:
            con.close()

    def delete_conversation(self, contact_uuid):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("DELETE FROM messages WHERE contact_uuid = ?",
                        (contact_uuid,))
            con.commit()
            return True
        finally:
            con.close()

    def get_conversations(self):
        """Список UUID контактов, с которыми есть переписка."""
        con = sqlite3.connect(MESSAGES_DB)
        try:
            rows = con.execute("""
                SELECT DISTINCT contact_uuid
                FROM messages
                ORDER BY timestamp DESC
            """).fetchall()
        finally:
            con.close()

        return [r[0] for r in rows]

    def count_messages(self, contact_uuid=None):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            if contact_uuid:
                row = con.execute(
                    "SELECT COUNT(*) FROM messages WHERE contact_uuid = ?",
                    (contact_uuid,)
                ).fetchone()
            else:
                row = con.execute("SELECT COUNT(*) FROM messages").fetchone()
            return row[0] if row else 0
        finally:
            con.close()

    def clear_all(self):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("DELETE FROM messages")
            con.commit()
            return True
        finally:
            con.close()


class ContactStore:
    """Хранилище контактов."""

    def __init__(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.contacts = self._load()

    def _load(self):
        if CONTACTS_FILE.exists():
            try:
                return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"contacts": []}

    def save(self):
        try:
            CONTACTS_FILE.write_text(
                json.dumps(self.contacts, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def add(self, contact):
        """Добавляет контакт."""
        for c in self.contacts["contacts"]:
            if c["uuid"] == contact.uuid:
                # обновляем
                c.update(contact.to_dict())
                self.save()
                return False  # уже был

        self.contacts["contacts"].append(contact.to_dict())
        self.save()
        return True

    def remove(self, uuid):
        before = len(self.contacts["contacts"])
        self.contacts["contacts"] = [
            c for c in self.contacts["contacts"] if c["uuid"] != uuid
        ]
        if len(self.contacts["contacts"]) < before:
            self.save()
            return True
        return False

    def get(self, uuid):
        for c in self.contacts["contacts"]:
            if c["uuid"] == uuid:
                return c
        return None

    def list_all(self):
        return self.contacts["contacts"]

    def count(self):
        return len(self.contacts["contacts"])

    def clear(self):
        self.contacts["contacts"] = []
        self.save()


class Settings:
    """Настройки приложения."""

    DEFAULT = {
        "theme": "gothic",
        "auto_connect": True,
        "notifications": True,
        "save_history": True,
        "read_receipts": False,
        "typing_indicator": True,
        "onion_address": None,
        "nickname": "anonymous",
        "first_run": True,
    }

    def __init__(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        if SETTINGS_FILE.exists():
            try:
                loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                for k, v in self.DEFAULT.items():
                    if k not in loaded:
                        loaded[k] = v
                return loaded
            except Exception:
                pass
        return dict(self.DEFAULT)

    def save(self):
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def reset(self):
        self.data = dict(self.DEFAULT)
        self.save()