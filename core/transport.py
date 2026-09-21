import threading
import time
import base64
from datetime import datetime

from core.protocol import (
    MessageType, make_hello, make_handshake, make_text,
    make_ack, make_ping, make_pong, make_bye, make_typing,
    make_online, make_read, make_edit, make_delete,
    make_file_start, make_file_chunk, make_file_end,
    make_file_accept, make_file_reject,
    make_group_create, make_group_invite, make_group_join,
    make_group_leave, make_group_message, make_group_info,
    make_fingerprint_verify, make_block,
    handle_message,
)
from core.crypto import (
    derive_shared_key, encrypt_message, decrypt_message,
)
from core.identity import Contact, bytes_to_public


class Transport:
    """Транспорт v0.2 — файлы, группы, очередь, редактирование."""

    def __init__(self, identity, queue=None, file_manager=None,
                 group_manager=None):
        self.identity = identity
        self.server = None
        self.connections = {}
        self.shared_keys = {}
        self.queue = queue
        self.file_manager = file_manager
        self.group_manager = group_manager

        self.on_message = None
        self.on_connect = None
        self.on_disconnect = None
        self.on_typing = None
        self.on_online = None
        self.on_file_start = None
        self.on_file_complete = None
        self.on_file_progress = None
        self.on_group_message = None
        self.on_group_invite = None
        self.on_read = None
        self.on_edit = None
        self.on_delete = None

        self.lock = threading.Lock()

    def set_server(self, server):
        self.server = server
        server.on_message = self._handle_incoming
        server.on_new_connection = self._on_new_connection
        server.on_disconnect = self._on_disconnect

    def _on_new_connection(self, client_id):
        if self.on_connect:
            try:
                self.on_connect(client_id, None)
            except Exception:
                pass

    def _on_disconnect(self, client_id):
        if self.on_disconnect:
            try:
                self.on_disconnect(client_id)
            except Exception:
                pass

    def _handle_incoming(self, client_id, data):
        result = handle_message(data)
        if result.get("error"):
            return

        msg_type = result["type"]
        payload = result["payload"]

        handlers = {
            MessageType.HELLO: self._handle_hello,
            MessageType.HANDSHAKE: self._handle_handshake,
            MessageType.TEXT: self._handle_text,
            MessageType.ACK: self._handle_ack,
            MessageType.PING: self._handle_ping,
            MessageType.PONG: self._handle_pong,
            MessageType.TYPING: self._handle_typing,
            MessageType.ONLINE: self._handle_online,
            MessageType.READ: self._handle_read,
            MessageType.EDIT: self._handle_edit,
            MessageType.DELETE: self._handle_delete,
            MessageType.FILE_START: self._handle_file_start,
            MessageType.FILE_CHUNK: self._handle_file_chunk,
            MessageType.FILE_END: self._handle_file_end,
            MessageType.FILE_ACCEPT: self._handle_file_accept,
            MessageType.FILE_REJECT: self._handle_file_reject,
            MessageType.GROUP_INVITE: self._handle_group_invite,
            MessageType.GROUP_JOIN: self._handle_group_join,
            MessageType.GROUP_LEAVE: self._handle_group_leave,
            MessageType.GROUP_MESSAGE: self._handle_group_message,
            MessageType.FINGERPRINT_VERIFY: self._handle_fingerprint,
            MessageType.CONTACT_BLOCK: self._handle_block,
        }

        handler = handlers.get(msg_type)
        if handler:
            try:
                handler(client_id, payload)
            except Exception:
                pass

    def _get_uuid_by_client(self, client_id):
        if not self.server:
            return None
        with self.server.lock:
            client = self.server.clients.get(client_id)
            return client.get("uuid") if client else None

    def _handle_hello(self, client_id, payload):
        uuid = payload.get("uuid")

        if self.server:
            self.server.set_client_uuid(client_id, uuid)
            self.server.send_to(client_id, make_handshake(self.identity))

    def _handle_handshake(self, client_id, payload):
        try:
            uuid = payload["uuid"]
            public_bytes = bytes.fromhex(payload["public_key_hex"])
            peer_public = bytes_to_public(public_bytes)
            shared_key = derive_shared_key(self.identity.private_key, peer_public)

            with self.lock:
                self.shared_keys[uuid] = shared_key

            contact = Contact(
                uuid=uuid,
                public_bytes=public_bytes,
                nickname=payload.get("nickname", "unknown"),
                onion_address=payload.get("onion"),
            )

            if self.on_connect:
                self.on_connect(client_id, contact)

            # пробуем отправить очередь
            self._process_queue(uuid)
        except Exception:
            pass

    def _handle_text(self, client_id, payload):
        try:
            uuid = self._get_uuid_by_client(client_id)
            if not uuid:
                return

            with self.lock:
                shared_key = self.shared_keys.get(uuid)

            if not shared_key:
                return

            data = payload.get("data")
            msg_id = payload.get("id")
            ts = payload.get("time")
            reply_to = payload.get("reply_to")

            plaintext = decrypt_message(shared_key, data)
            if plaintext is None:
                return

            if self.server:
                self.server.send_to(client_id, make_ack(msg_id))

            if self.on_message:
                self.on_message(uuid, plaintext, msg_id, ts, reply_to)

            # отправляем READ
            if self.server:
                self.server.send_to(client_id, make_read(msg_id))
        except Exception:
            pass

    def _handle_ack(self, client_id, payload):
        pass

    def _handle_ping(self, client_id, payload):
        if self.server:
            self.server.send_to(client_id, make_pong())

    def _handle_pong(self, client_id, payload):
        pass

    def _handle_typing(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if self.on_typing and uuid:
            try:
                self.on_typing(uuid, payload.get("typing", False))
            except Exception:
                pass

    def _handle_online(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if self.on_online and uuid:
            try:
                self.on_online(uuid, payload.get("online", True))
            except Exception:
                pass

    def _handle_read(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if self.on_read and uuid:
            try:
                self.on_read(uuid, payload.get("id"))
            except Exception:
                pass

    def _handle_edit(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if not uuid or not self.on_edit:
            return

        with self.lock:
            shared_key = self.shared_keys.get(uuid)

        if not shared_key:
            return

        plaintext = decrypt_message(shared_key, payload.get("data"))
        if plaintext:
            try:
                self.on_edit(uuid, payload.get("id"), plaintext)
            except Exception:
                pass

    def _handle_delete(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if self.on_delete and uuid:
            try:
                self.on_delete(uuid, payload.get("id"))
            except Exception:
                pass

    def _handle_file_start(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)

        if self.file_manager:
            transfer, error = self.file_manager.handle_file_start(payload, uuid)

            if transfer and self.on_file_start:
                try:
                    self.on_file_start(uuid, transfer)
                except Exception:
                    pass

            if self.server:
                self.server.send_to(client_id, make_file_accept(
                    payload.get("file_id")
                ))

    def _handle_file_chunk(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)

        if self.file_manager:
            self.file_manager.handle_file_chunk(payload, uuid)

            file_id = payload.get("file_id")
            transfer = self.file_manager.get_transfer(file_id)

            if transfer and self.on_file_progress:
                try:
                    self.on_file_progress(uuid, file_id, transfer.progress())
                except Exception:
                    pass

    def _handle_file_end(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)

        if not self.file_manager:
            return

        path, error = self.file_manager.handle_file_end(payload, uuid)

        if path and self.on_file_complete:
            try:
                self.on_file_complete(uuid, payload.get("file_id"), str(path))
            except Exception:
                pass

    def _handle_file_accept(self, client_id, payload):
        pass

    def _handle_file_reject(self, client_id, payload):
        pass

    def _handle_group_invite(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if self.on_group_invite and uuid:
            try:
                self.on_group_invite(uuid, payload)
            except Exception:
                pass

    def _handle_group_join(self, client_id, payload):
        pass

    def _handle_group_leave(self, client_id, payload):
        pass

    def _handle_group_message(self, client_id, payload):
        uuid = self._get_uuid_by_client(client_id)
        if self.on_group_message and uuid:
            try:
                self.on_group_message(uuid, payload)
            except Exception:
                pass

    def _handle_fingerprint(self, client_id, payload):
        pass

    def _handle_block(self, client_id, payload):
        if self.server:
            self.server.send_to(client_id, make_block("ack"))
            time.sleep(0.5)
            self.server.stop()

    def _process_queue(self, uuid):
        """Пробует отправить накопившиеся сообщения."""
        if not self.queue:
            return

        for _ in range(20):
            message = self.queue.dequeue(uuid)
            if not message:
                break

            try:
                success = self.send_raw(uuid, message["payload"])
                if not success:
                    self.queue.enqueue(
                        uuid, message["type"], message["payload"],
                        priority=message.get("priority", 0)
                    )
                    break
            except Exception:
                break

    def connect_to(self, onion_address, timeout=60):
        from core.network import TorSocket

        ts = TorSocket()
        success, error = ts.connect(onion_address, timeout=timeout)

        if not success:
            return False, error

        success, error = ts.send(make_hello(self.identity))

        if not success:
            ts.close()
            return False, error

        thread = threading.Thread(
            target=self._listen_connection,
            args=(onion_address, ts),
            daemon=True,
        )
        thread.start()

        return True, None

    def _listen_connection(self, onion_address, ts):
        ts.sock.settimeout(1.0)

        while ts.is_connected():
            try:
                data = ts.recv()
                if not data:
                    break

                result = handle_message(data)
                if result.get("error"):
                    continue

                msg_type = result["type"]
                payload = result["payload"]

                if msg_type == MessageType.HANDSHAKE:
                    self._handle_outgoing_handshake(onion_address, payload)
                elif msg_type == MessageType.TEXT:
                    pass
                elif msg_type == MessageType.PING:
                    ts.send(make_pong())
                elif msg_type == MessageType.BYE:
                    break
            except Exception:
                time.sleep(0.1)

        ts.close()

    def _handle_outgoing_handshake(self, onion_address, payload):
        try:
            uuid = payload["uuid"]
            public_bytes = bytes.fromhex(payload["public_key_hex"])
            peer_public = bytes_to_public(public_bytes)
            shared_key = derive_shared_key(self.identity.private_key, peer_public)

            with self.lock:
                self.shared_keys[uuid] = shared_key

            contact = Contact(
                uuid=uuid,
                public_bytes=public_bytes,
                nickname=payload.get("nickname", "unknown"),
                onion_address=onion_address,
            )

            if self.on_connect:
                self.on_connect(onion_address, contact)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════
    # ОТПРАВКА
    # ═══════════════════════════════════════════════════════

    def send_message(self, uuid, text, reply_to=None):
        """Отправляет личное сообщение. Если офлайн — в очередь."""
        with self.lock:
            shared_key = self.shared_keys.get(uuid)

        if not shared_key:
            return False, "Нет общего ключа"

        try:
            encrypted = encrypt_message(shared_key, text)
        except Exception as e:
            return False, f"Ошибка шифрования: {e}"

        packet = make_text(encrypted, reply_to=reply_to)

        # если онлайн — отправляем
        if self.server:
            client_id = self.server.get_client_by_uuid(uuid)
            if client_id:
                success, error = self.server.send_to(client_id, packet)
                if success:
                    return True, None

        # офлайн — в очередь
        if self.queue:
            self.queue.enqueue(uuid, "text", packet, priority=1)
            return True, "queued"

        return False, "Контакт не подключён"

    def send_raw(self, uuid, packet):
        """Отправляет сырой пакет."""
        if not self.server:
            return False

        client_id = self.server.get_client_by_uuid(uuid)
        if not client_id:
            return False

        success, _ = self.server.send_to(client_id, packet)
        return success

    def send_file(self, uuid, file_path):
        """Отправляет файл."""
        if not self.file_manager:
            return False, "FileManager не инициализирован"

        transfer, packets = self.file_manager.prepare_outgoing(file_path, uuid)

        if not transfer:
            return False, packets

        for packet in packets:
            success = self.send_raw(uuid, packet)
            if not success:
                return False, "Ошибка отправки"

        return True, transfer.file_id

    def send_group_message(self, group_id, text):
        """
        Отправляет групповое сообщение.

        ИСПРАВЛЕНО v0.2.1:
        Пустой encrypted_per_member — это НОРМАЛЬНО.
        Значит ты один в группе или все офлайн.
        Сообщение всё равно сохраняется в истории.
        """
        if not self.group_manager:
            return False, "GroupManager не инициализирован"

        encrypted_per_member, message_data = self.group_manager.send_message(
            group_id, text, self.identity.uuid
        )

        if message_data is None:
            return False, "Ошибка создания сообщения"

        # Отправляем всем, у кого есть ключ
        for member_uuid, encrypted in encrypted_per_member.items():
            packet = make_group_message(
                group_id=group_id,
                encrypted_data=encrypted,
                msg_id=message_data["msg_id"],
                sender_uuid=self.identity.uuid,
            )
            self.send_raw(member_uuid, packet)

        # Всегда сохраняем в локальную историю
        self.group_manager.add_message_to_history(group_id, message_data)

        return True, None

    def send_read(self, uuid, msg_id):
        if self.server:
            client_id = self.server.get_client_by_uuid(uuid)
            if client_id:
                self.server.send_to(client_id, make_read(msg_id))

    def send_edit(self, uuid, msg_id, new_text):
        with self.lock:
            shared_key = self.shared_keys.get(uuid)

        if not shared_key:
            return False

        try:
            encrypted = encrypt_message(shared_key, new_text)
        except Exception:
            return False

        packet = make_edit(msg_id, encrypted)
        return self.send_raw(uuid, packet)

    def send_delete(self, uuid, msg_id):
        return self.send_raw(uuid, make_delete(msg_id))

    def broadcast_typing(self, uuid, is_typing=True):
        return self.send_raw(uuid, make_typing(is_typing))

    def broadcast_online(self, uuid, online=True):
        return self.send_raw(uuid, make_online(online))

    def is_contact_online(self, uuid):
        if not self.server:
            return False
        return self.server.get_client_by_uuid(uuid) is not None

    def get_shared_key(self, uuid):
        with self.lock:
            return self.shared_keys.get(uuid)

    def shutdown(self):
        if self.server:
            self.server.stop()
        with self.lock:
            self.connections = {}