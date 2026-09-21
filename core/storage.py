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
FILES_META = STORAGE_DIR / "files_meta.json"


class MessageStore:
    """Хранилище сообщений (SQLite, шифрование)."""

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
                read INTEGER DEFAULT 0,
                edited INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0,
                reply_to TEXT,
                is_file INTEGER DEFAULT 0,
                file_name TEXT,
                file_size INTEGER
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_contact
            ON messages(contact_uuid, timestamp)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_unread
            ON messages(contact_uuid, read)
        """)
        con.commit()
        con.close()

    def add_message(self, msg_id, contact_uuid, direction,
                    plaintext, timestamp=None, reply_to=None,
                    is_file=False, file_name=None, file_size=0):
        if self.encryption_key:
            encrypted = encrypt_bytes(self.encryption_key, plaintext)
            encrypted_b64 = base64.b64encode(encrypted).decode("ascii")
        else:
            data = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
            encrypted_b64 = base64.b64encode(data).decode("ascii")

        ts = timestamp or datetime.now().isoformat()

        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("""
                INSERT OR REPLACE INTO messages
                (msg_id, contact_uuid, direction, encrypted_data, timestamp,
                 reply_to, is_file, file_name, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (msg_id, contact_uuid, direction, encrypted_b64, ts,
                  reply_to, 1 if is_file else 0, file_name, file_size))
            con.commit()
            return True
        except Exception:
            return False
        finally:
            con.close()

    def get_messages(self, contact_uuid, limit=100, include_deleted=False):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            where = "contact_uuid = ?"
            params = [contact_uuid]

            if not include_deleted:
                where += " AND deleted = 0"

            rows = con.execute(f"""
                SELECT msg_id, direction, encrypted_data, timestamp,
                       read, edited, reply_to, is_file, file_name, file_size
                FROM messages
                WHERE {where}
                ORDER BY timestamp ASC
                LIMIT ?
            """, params + [limit]).fetchall()
        finally:
            con.close()

        result = []
        for row in rows:
            (msg_id, direction, encrypted_b64, ts, read,
             edited, reply_to, is_file, file_name, file_size) = row

            try:
                blob = base64.b64decode(encrypted_b64)

                if self.encryption_key:
                    plaintext = decrypt_bytes(self.encryption_key, blob)
                    text = plaintext.decode("utf-8") if plaintext else "[ошибка]"
                else:
                    text = blob.decode("utf-8")

                result.append({
                    "id": msg_id,
                    "direction": direction,
                    "text": text,
                    "timestamp": ts,
                    "read": bool(read),
                    "edited": bool(edited),
                    "reply_to": reply_to,
                    "is_file": bool(is_file),
                    "file_name": file_name,
                    "file_size": file_size,
                })
            except Exception:
                continue

        return result

    def mark_read(self, msg_id):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("UPDATE messages SET read = 1 WHERE msg_id = ?", (msg_id,))
            con.commit()
            return True
        finally:
            con.close()

    def mark_all_read(self, contact_uuid):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute(
                "UPDATE messages SET read = 1 WHERE contact_uuid = ?",
                (contact_uuid,)
            )
            con.commit()
            return True
        finally:
            con.close()

    def edit_message(self, msg_id, new_text):
        if not self.encryption_key:
            return False

        encrypted = encrypt_bytes(self.encryption_key, new_text)
        encrypted_b64 = base64.b64encode(encrypted).decode("ascii")

        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute(
                "UPDATE messages SET encrypted_data = ?, edited = 1 WHERE msg_id = ?",
                (encrypted_b64, msg_id)
            )
            con.commit()
            return True
        finally:
            con.close()

    def delete_message(self, msg_id):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("UPDATE messages SET deleted = 1 WHERE msg_id = ?", (msg_id,))
            con.commit()
            return True
        finally:
            con.close()

    def delete_conversation(self, contact_uuid):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            con.execute("UPDATE messages SET deleted = 1 WHERE contact_uuid = ?",
                        (contact_uuid,))
            con.commit()
            return True
        finally:
            con.close()

    def get_unread_count(self, contact_uuid):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            row = con.execute("""
                SELECT COUNT(*) FROM messages
                WHERE contact_uuid = ? AND read = 0
                AND direction = 'in' AND deleted = 0
            """, (contact_uuid,)).fetchone()
            return row[0] if row else 0
        finally:
            con.close()

    def get_total_unread(self):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            row = con.execute("""
                SELECT COUNT(*) FROM messages
                WHERE read = 0 AND direction = 'in' AND deleted = 0
            """).fetchone()
            return row[0] if row else 0
        finally:
            con.close()

    def get_conversations(self):
        con = sqlite3.connect(MESSAGES_DB)
        try:
            rows = con.execute("""
                SELECT contact_uuid, MAX(timestamp) as last_ts
                FROM messages
                WHERE deleted = 0
                GROUP BY contact_uuid
                ORDER BY last_ts DESC
            """).fetchall()
        finally:
            con.close()
        return [r[0] for r in rows]

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
        for c in self.contacts["contacts"]:
            if c["uuid"] == contact.uuid:
                c.update(contact.to_dict())
                self.save()
                return False

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

    def update(self, uuid, **kwargs):
        c = self.get(uuid)
        if not c:
            return False
        for k, v in kwargs.items():
            if k in ("nickname", "onion_address", "verified"):
                c[k] = v
        self.save()
        return True

    def list_all(self):
        return self.contacts["contacts"]

    def count(self):
        return len(self.contacts["contacts"])

    def clear(self):
        self.contacts["contacts"] = []
        self.save()


class Settings:
    """Настройки."""

    DEFAULT = {
        "theme": "gothic",
        "auto_connect": True,
        "notifications": True,
        "sounds": True,
        "save_history": True,
        "read_receipts": True,
        "typing_indicator": True,
        "onion_address": None,
        "nickname": "anonymous",
        "auto_delete_days": 0,
        "language": "ru",
        "tray_enabled": True,
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


class FileMetaStore:
    """Метаданные полученных файлов."""

    def __init__(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.files = self._load()

    def _load(self):
        if FILES_META.exists():
            try:
                return json.loads(FILES_META.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"files": []}

    def save(self):
        try:
            FILES_META.write_text(
                json.dumps(self.files, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def add(self, file_id, filename, size, sender_uuid, path):
        self.files["files"].append({
            "file_id": file_id,
            "filename": filename,
            "size": size,
            "sender_uuid": sender_uuid,
            "path": str(path),
            "received": datetime.now().isoformat(),
        })
        self.save()

    def list_all(self):
        return self.files["files"]

    def get(self, file_id):
        for f in self.files["files"]:
            if f["file_id"] == file_id:
                return f
        return None