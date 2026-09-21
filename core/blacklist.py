import json
from pathlib import Path
from datetime import datetime


BLACKLIST_FILE = Path.home() / ".nocturne" / "blacklist.json"


class Blacklist:
    """Чёрный список контактов."""

    def __init__(self):
        BLACKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self):
        if BLACKLIST_FILE.exists():
            try:
                return json.loads(BLACKLIST_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"blocked": {}}

    def _save(self):
        try:
            BLACKLIST_FILE.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def block(self, uuid, reason=""):
        """Блокирует контакт."""
        self.data["blocked"][uuid] = {
            "reason": reason,
            "blocked_at": datetime.now().isoformat(),
        }
        self._save()
        return True

    def unblock(self, uuid):
        """Разблокирует контакт."""
        if uuid in self.data["blocked"]:
            del self.data["blocked"][uuid]
            self._save()
            return True
        return False

    def is_blocked(self, uuid):
        """Проверяет, заблокирован ли."""
        return uuid in self.data["blocked"]

    def get_reason(self, uuid):
        """Причина блокировки."""
        entry = self.data["blocked"].get(uuid)
        return entry.get("reason", "") if entry else None

    def list_blocked(self):
        """Список заблокированных."""
        return [
            {
                "uuid": uuid,
                "reason": info.get("reason", ""),
                "blocked_at": info.get("blocked_at"),
            }
            for uuid, info in self.data["blocked"].items()
        ]

    def clear(self):
        """Очищает чёрный список."""
        self.data["blocked"] = {}
        self._save()


class AutoDelete:
    """Автоочистка сообщений."""

    def __init__(self, storage):
        self.storage = storage

    def delete_older_than(self, days):
        """Удаляет сообщения старше N дней."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        deleted = 0

        conversations = self.storage.get_conversations()

        for uuid in conversations:
            messages = self.storage.get_messages(uuid, limit=10000)

            for m in messages:
                try:
                    ts = datetime.fromisoformat(m.get("timestamp", ""))
                except Exception:
                    continue

                if ts < cutoff:
                    self.storage.delete_message(m["id"])
                    deleted += 1

        return deleted

    def delete_read_messages(self, contact_uuid):
        """Удаляет прочитанные сообщения с контактом."""
        # заглушка — реализация зависит от того, как помечаются прочитанные
        return 0


class PanicButton:
    """Паник-кнопка — стирает всё."""

    def __init__(self, identity_file, message_store, contact_store,
                 group_manager=None):
        self.identity_file = identity_file
        self.message_store = message_store
        self.contact_store = contact_store
        self.group_manager = group_manager

    def wipe_messages(self):
        """Стирает все сообщения."""
        try:
            self.message_store.clear_all()
            return True
        except Exception:
            return False

    def wipe_contacts(self):
        """Стирает все контакты."""
        try:
            self.contact_store.clear()
            return True
        except Exception:
            return False

    def wipe_groups(self):
        """Стирает все группы."""
        if not self.group_manager:
            return False

        try:
            for group in list(self.group_manager.list_groups()):
                self.group_manager.delete_group(group.group_id)
            return True
        except Exception:
            return False

    def wipe_all(self):
        """Полное стирание (кроме identity)."""
        self.wipe_messages()
        self.wipe_contacts()
        self.wipe_groups()

        # чистим файлы
        from core.queue import QUEUE_FILE
        from core.blacklist import BLACKLIST_FILE
        from pathlib import Path

        for f in [QUEUE_FILE, BLACKLIST_FILE]:
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass

        return True

    def full_reset(self):
        """Полное удаление — включая identity."""
        self.wipe_all()

        try:
            if self.identity_file.exists():
                self.identity_file.unlink()
            return True
        except Exception:
            return False