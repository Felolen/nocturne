"""
Логика для UI групп.
"""

import secrets
from datetime import datetime

from core.groups import GroupManager, Group
from core.protocol import (
    make_group_create, make_group_invite, make_group_join,
    make_group_leave, make_group_message, make_group_info,
)


class GroupUIHelper:
    """Помощник для работы с группами в UI."""

    def __init__(self, group_manager, transport, identity):
        self.groups = group_manager
        self.transport = transport
        self.identity = identity

    def create_and_broadcast(self, name, member_uuids):
        """
        Создаёт группу и рассылает приглашения.
        """
        group = self.groups.create_group(name, member_uuids)

        # рассылаем приглашения
        for member_uuid in member_uuids:
            invite_packet = make_group_invite(
                group_id=group.group_id,
                name=group.name,
                inviter_uuid=self.identity.uuid,
                inviter_nickname=self.identity.nickname,
            )

            if self.transport:
                self.transport.send_raw(member_uuid, invite_packet)

        return group

    def send_to_group(self, group_id, text):
        """
        Отправляет сообщение в группу.
        Возвращает (success, error).
        """
        encrypted_per_member, message_data = self.groups.send_message(
            group_id, text, self.identity.uuid
        )

        if not encrypted_per_member:
            return False, "Не удалось зашифровать"

        group = self.groups.get_group(group_id)

        # отправляем каждому участнику
        for member_uuid, encrypted_data in encrypted_per_member.items():
            packet = make_group_message(
                group_id=group_id,
                encrypted_data=encrypted_data,
                msg_id=message_data["msg_id"],
                sender_uuid=self.identity.uuid,
            )

            if self.transport:
                self.transport.send_raw(member_uuid, packet)

        # сохраняем в историю локально
        self.groups.add_message_to_history(group_id, message_data)

        return True, None

    def handle_incoming_invite(self, payload, sender_uuid):
        """Обработка входящего приглашения в группу."""
        group_id = payload.get("group_id")
        name = payload.get("name")
        inviter_uuid = payload.get("inviter_uuid")
        inviter_nickname = payload.get("inviter_nickname", "unknown")

        if not group_id or not name:
            return None

        # создаём локальную группу
        group = Group(
            group_id=group_id,
            name=name,
            creator_uuid=inviter_uuid,
        )

        # я — участник
        group.add_member(
            self.identity.uuid,
            self.identity.nickname,
            role="member",
        )

        # пригласивший — админ
        group.add_member(inviter_uuid, inviter_nickname, role="admin")

        self.groups.groups[group_id] = group
        self.groups._save_group(group)

        return group

    def accept_invite(self, group_id):
        """Принять приглашение — уведомить создателя."""
        group = self.groups.get_group(group_id)
        if not group:
            return False

        # отправляем JOIN создателю
        packet = make_group_join(
            group_id=group_id,
            uuid=self.identity.uuid,
            nickname=self.identity.nickname,
        )

        creator_uuid = group.creator_uuid

        if self.transport:
            self.transport.send_raw(creator_uuid, packet)

        return True

    def leave_group(self, group_id):
        """Выйти из группы."""
        group = self.groups.get_group(group_id)
        if not group:
            return False

        # уведомляем всех
        packet = make_group_leave(
            group_id=group_id,
            uuid=self.identity.uuid,
        )

        for member_uuid in group.members.keys():
            if member_uuid == self.identity.uuid:
                continue
            if self.transport:
                self.transport.send_raw(member_uuid, packet)

        # удаляем локально
        self.groups.delete_group(group_id)

        return True

    def handle_member_join(self, payload, sender_uuid):
        """Обработка присоединения нового участника."""
        group_id = payload.get("group_id")
        uuid = payload.get("uuid")
        nickname = payload.get("nickname", "unknown")

        if not group_id or not uuid:
            return False

        group = self.groups.get_group(group_id)
        if not group:
            return False

        group.add_member(uuid, nickname)
        self.groups._save_group(group)

        return True

    def handle_member_leave(self, payload, sender_uuid):
        """Обработка выхода участника."""
        group_id = payload.get("group_id")
        uuid = payload.get("uuid")

        if not group_id or not uuid:
            return False

        group = self.groups.get_group(group_id)
        if not group:
            return False

        group.remove_member(uuid)
        self.groups._save_group(group)

        return True

    def handle_group_message(self, payload, sender_uuid):
        """Обработка входящего группового сообщения."""
        group_id = payload.get("group_id")
        encrypted_data = payload.get("data")
        msg_id = payload.get("id")
        timestamp = payload.get("time")

        if not group_id or not encrypted_data:
            return None

        # расшифровываем
        message_data, error = self.groups.receive_message(
            group_id, encrypted_data, sender_uuid, msg_id, timestamp
        )

        return message_data