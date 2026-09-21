import uuid
import secrets
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from core.crypto import encrypt_message, decrypt_message


GROUPS_DIR = Path.home() / ".nocturne" / "groups"


class Group:
    """Групповой чат."""

    def __init__(self, group_id, name, creator_uuid):
        self.group_id = group_id
        self.name = name
        self.creator_uuid = creator_uuid
        self.members = {}  # uuid -> {nickname, role, joined}
        self.messages = []  # список сообщений
        self.created = datetime.now().isoformat()
        self.topic = ""

    def add_member(self, uuid, nickname, role="member"):
        """Добавляет участника."""
        if uuid not in self.members:
            self.members[uuid] = {
                "nickname": nickname,
                "role": role,
                "joined": datetime.now().isoformat(),
            }
            return True
        return False

    def remove_member(self, uuid):
        """Удаляет участника."""
        if uuid in self.members:
            del self.members[uuid]
            return True
        return False

    def is_admin(self, uuid):
        """Проверяет, админ ли участник."""
        member = self.members.get(uuid)
        return member and member.get("role") == "admin"

    def get_member(self, uuid):
        return self.members.get(uuid)

    def member_count(self):
        return len(self.members)

    def to_dict(self):
        return {
            "group_id": self.group_id,
            "name": self.name,
            "creator_uuid": self.creator_uuid,
            "members": self.members,
            "created": self.created,
            "topic": self.topic,
        }

    @staticmethod
    def from_dict(data):
        group = Group(
            data["group_id"],
            data["name"],
            data["creator_uuid"],
        )
        group.members = data.get("members", {})
        group.created = data.get("created", datetime.now().isoformat())
        group.topic = data.get("topic", "")
        return group


class GroupManager:
    """Управление группами."""

    def __init__(self, identity, encryption_key_getter):
        GROUPS_DIR.mkdir(parents=True, exist_ok=True)
        self.identity = identity
        self.key_getter = encryption_key_getter
        self.groups = {}  # group_id -> Group
        self._load_all()

    def _load_all(self):
        """Загружает все группы с диска."""
        if not GROUPS_DIR.exists():
            return

        for file in GROUPS_DIR.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                group = Group.from_dict(data)
                self.groups[group.group_id] = group
            except Exception:
                continue

    def _save_group(self, group):
        """Сохраняет группу на диск."""
        try:
            path = GROUPS_DIR / f"{group.group_id}.json"
            path.write_text(
                json.dumps(group.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def create_group(self, name, members=None):
        """
        Создаёт новую группу.
        members — список UUID участников.
        """
        group_id = f"grp-{secrets.token_hex(8)}"

        group = Group(
            group_id=group_id,
            name=name,
            creator_uuid=self.identity.uuid,
        )

        # создатель — админ
        group.add_member(
            self.identity.uuid,
            self.identity.nickname,
            role="admin",
        )

        # добавляем участников
        if members:
            for uuid in members:
                group.add_member(uuid, "member", role="member")

        self.groups[group_id] = group
        self._save_group(group)

        return group

    def delete_group(self, group_id):
        if group_id in self.groups:
            del self.groups[group_id]
            try:
                path = GROUPS_DIR / f"{group_id}.json"
                if path.exists():
                    path.unlink()
            except Exception:
                pass
            return True
        return False

    def get_group(self, group_id):
        return self.groups.get(group_id)

    def list_groups(self):
        return list(self.groups.values())

    def add_member(self, group_id, uuid, nickname):
        group = self.groups.get(group_id)
        if not group:
            return False, "Группа не найдена"

        if uuid in group.members:
            return False, "Уже участник"

        group.add_member(uuid, nickname)
        self._save_group(group)
        return True, None

    def remove_member(self, group_id, uuid):
        group = self.groups.get(group_id)
        if not group:
            return False, "Группа не найдена"

        if group.remove_member(uuid):
            self._save_group(group)
            return True, None
        return False, "Участник не найден"

    def promote_to_admin(self, group_id, uuid, by_uuid):
        """Повышает участника до админа."""
        group = self.groups.get(group_id)
        if not group:
            return False, "Группа не найдена"

        if not group.is_admin(by_uuid):
            return False, "Только админ может повышать"

        member = group.members.get(uuid)
        if not member:
            return False, "Участник не найден"

        member["role"] = "admin"
        self._save_group(group)
        return True, None

    def send_message(self, group_id, text, sender_uuid=None):
        """
        Отправляет сообщение в группу.
        Возвращает (encrypted_per_member, message_data) или (None, error).
        """
        group = self.groups.get(group_id)
        if not group:
            return None, "Группа не найдена"

        sender_uuid = sender_uuid or self.identity.uuid
        msg_id = f"gmsg-{secrets.token_hex(8)}"
        timestamp = datetime.now().isoformat()

        # шифруем для каждого участника отдельно
        encrypted_per_member = {}

        for member_uuid in group.members.keys():
            if member_uuid == self.identity.uuid:
                continue

            shared_key = self.key_getter(member_uuid)
            if not shared_key:
                continue

            encrypted = encrypt_message(shared_key, text)
            encrypted_per_member[member_uuid] = encrypted

        message_data = {
            "group_id": group_id,
            "msg_id": msg_id,
            "sender_uuid": sender_uuid,
            "text": text,
            "timestamp": timestamp,
        }

        return encrypted_per_member, message_data

    def add_message_to_history(self, group_id, message_data):
        """Добавляет сообщение в историю группы."""
        group = self.groups.get(group_id)
        if not group:
            return False

        group.messages.append(message_data)

        # ограничиваем историю
        if len(group.messages) > 1000:
            group.messages = group.messages[-1000:]

        self._save_group(group)
        return True

    def get_messages(self, group_id, limit=100):
        group = self.groups.get(group_id)
        if not group:
            return []
        return group.messages[-limit:]

    def receive_message(self, group_id, encrypted_data, sender_uuid,
                         msg_id, timestamp):
        """
        Принимает входящее групповое сообщение.
        Расшифровывает и добавляет в историю.
        """
        group = self.groups.get(group_id)
        if not group:
            return None, "Группа не найдена"

        # расшифровываем — но нам нужен ключ ОТПРАВИТЕЛЯ
        shared_key = self.key_getter(sender_uuid)
        if not shared_key:
            return None, "Нет ключа с отправителем"

        plaintext = decrypt_message(shared_key, encrypted_data)
        if plaintext is None:
            return None, "Ошибка расшифровки"

        message_data = {
            "group_id": group_id,
            "msg_id": msg_id,
            "sender_uuid": sender_uuid,
            "text": plaintext,
            "timestamp": timestamp,
        }

        self.add_message_to_history(group_id, message_data)

        return message_data, None


class GroupCrypto:
    """
    Утилита для группового шифрования.
    Каждое сообщение шифруется отдельно для каждого участника.
    """

    @staticmethod
    def get_recipients(group, my_uuid):
        """Возвращает список UUID получателей (без меня)."""
        return [u for u in group.members.keys() if u != my_uuid]

    @staticmethod
    def group_fingerprint(group):
        """Возвращает отпечаток группы."""
        import hashlib
        members_str = ",".join(sorted(group.members.keys()))
        return hashlib.sha256(
            (group.group_id + members_str).encode()
        ).hexdigest()[:16].upper()