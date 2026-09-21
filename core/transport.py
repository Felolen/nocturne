import threading
import time
from datetime import datetime

from core.protocol import (
    MessageType, make_hello, make_handshake, make_text,
    make_ack, make_ping, make_pong, make_bye, make_typing,
    make_online, handle_message, get_message_name,
)
from core.crypto import derive_shared_key, encrypt_message, decrypt_message
from core.identity import Contact, bytes_to_public


class Transport:
    """
    Транспорт: управляет соединениями, отправкой, приёмом,
    обработкой протокола.
    """

    def __init__(self, identity):
        self.identity = identity
        self.server = None
        self.connections = {}  # uuid -> TorSocket
        self.shared_keys = {}  # uuid -> shared AES key
        self.on_message = None
        self.on_connect = None
        self.on_disconnect = None
        self.on_typing = None
        self.on_online = None
        self.lock = threading.Lock()

    def set_server(self, server):
        """Устанавливает Tor-сервер."""
        self.server = server
        server.on_message = self._handle_incoming
        server.on_new_connection = self._on_new_connection
        server.on_disconnect = self._on_disconnect

    def _on_new_connection(self, client_id):
        """Новое входящее соединение."""
        if self.on_connect:
            try:
                self.on_connect(client_id, None)
            except Exception:
                pass

    def _on_disconnect(self, client_id):
        """Отключение."""
        if self.on_disconnect:
            try:
                self.on_disconnect(client_id)
            except Exception:
                pass

    def _handle_incoming(self, client_id, data):
        """Обработка входящего пакета."""
        result = handle_message(data)

        if result.get("error"):
            return

        msg_type = result["type"]
        payload = result["payload"]

        if msg_type == MessageType.HELLO:
            self._handle_hello(client_id, payload)

        elif msg_type == MessageType.HANDSHAKE:
            self._handle_handshake(client_id, payload)

        elif msg_type == MessageType.TEXT:
            self._handle_text(client_id, payload)

        elif msg_type == MessageType.ACK:
            self._handle_ack(client_id, payload)

        elif msg_type == MessageType.PING:
            if self.server:
                self.server.send_to(client_id, make_pong())

        elif msg_type == MessageType.PONG:
            pass

        elif msg_type == MessageType.TYPING:
            if self.on_typing:
                try:
                    self.on_typing(client_id, payload.get("typing", False))
                except Exception:
                    pass

        elif msg_type == MessageType.ONLINE:
            if self.on_online:
                try:
                    self.on_online(client_id, payload.get("online", True))
                except Exception:
                    pass

        elif msg_type == MessageType.BYE:
            pass

    def _handle_hello(self, client_id, payload):
        """Получили HELLO — отвечаем HANDSHAKE."""
        uuid = payload.get("uuid")

        if self.server:
            self.server.set_client_uuid(client_id, uuid)

        if self.server:
            self.server.send_to(client_id, make_handshake(self.identity))

    def _handle_handshake(self, client_id, payload):
        """Получили HANDSHAKE — вычисляем общий ключ."""
        try:
            uuid = payload["uuid"]
            public_bytes = bytes.fromhex(payload["public_key_hex"])
            peer_public = bytes_to_public(public_bytes)

            shared_key = derive_shared_key(self.identity.private_key, peer_public)

            with self.lock:
                self.shared_keys[uuid] = shared_key

            # создаём контакт
            contact = Contact(
                uuid=uuid,
                public_bytes=public_bytes,
                nickname=payload.get("nickname", "unknown"),
                onion_address=payload.get("onion"),
            )

            if self.on_connect:
                try:
                    self.on_connect(client_id, contact)
                except Exception:
                    pass
        except Exception:
            pass

    def _handle_text(self, client_id, payload):
        """Расшифровываем входящее сообщение."""
        try:
            data = payload.get("data")
            msg_id = payload.get("id")
            ts = payload.get("time")

            uuid = None
            if self.server:
                with self.server.lock:
                    if client_id in self.server.clients:
                        uuid = self.server.clients[client_id].get("uuid")

            if not uuid:
                return

            with self.lock:
                shared_key = self.shared_keys.get(uuid)

            if not shared_key:
                return

            plaintext = decrypt_message(shared_key, data)

            if plaintext is None:
                return

            if self.server:
                self.server.send_to(client_id, make_ack(msg_id))

            if self.on_message:
                try:
                    self.on_message(uuid, plaintext, msg_id, ts)
                except Exception:
                    pass
        except Exception:
            pass

    def _handle_ack(self, client_id, payload):
        pass

    def connect_to(self, onion_address, timeout=60):
        """
        Подключается к другому пользователю через Tor.
        Возвращает (success, error).
        """
        from core.network import TorSocket

        ts = TorSocket()
        success, error = ts.connect(onion_address, timeout=timeout)

        if not success:
            return False, error

        # отправляем HELLO
        success, error = ts.send(make_hello(self.identity))

        if not success:
            ts.close()
            return False, error

        # слушаем ответ в отдельном потоке
        thread = threading.Thread(
            target=self._listen_connection,
            args=(onion_address, ts),
            daemon=True,
        )
        thread.start()

        return True, None

    def _listen_connection(self, onion_address, ts):
        """Слушает соединение с конкретным контактом."""
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
                    self._handle_outgoing_text(onion_address, payload)

                elif msg_type == MessageType.PING:
                    ts.send(make_pong())

                elif msg_type == MessageType.PONG:
                    pass

                elif msg_type == MessageType.BYE:
                    break
            except Exception:
                time.sleep(0.1)
                continue

        ts.close()

    def _handle_outgoing_handshake(self, onion_address, payload):
        """Обработка handshake на исходящем соединении."""
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

    def _handle_outgoing_text(self, onion_address, payload):
        """Обработка сообщения на исходящем соединении."""
        try:
            with self.lock:
                uuid = None
                for u, key in self.shared_keys.items():
                    pass

            # пока просто пробрасываем
        except Exception:
            pass

    def send_message(self, uuid, text):
        """
        Отправляет сообщение контакту.
        Возвращает (success, error).
        """
        with self.lock:
            shared_key = self.shared_keys.get(uuid)

        if not shared_key:
            return False, "Нет общего ключа с контактом"

        encrypted = encrypt_message(shared_key, text)
        packet = make_text(encrypted)

        # если есть сервер и клиент подключён — через сервер
        if self.server:
            client_id = self.server.get_client_by_uuid(uuid)
            if client_id:
                return self.server.send_to(client_id, packet)

        return False, "Контакт не подключён"

    def broadcast_typing(self, uuid, is_typing=True):
        """Уведомляет контакт, что печатаем."""
        if not self.server:
            return False

        client_id = self.server.get_client_by_uuid(uuid)
        if not client_id:
            return False

        return self.server.send_to(client_id, make_typing(is_typing))

    def broadcast_online(self, uuid, online=True):
        """Уведомляет контакт об online-статусе."""
        if not self.server:
            return False

        client_id = self.server.get_client_by_uuid(uuid)
        if not client_id:
            return False

        return self.server.send_to(client_id, make_online(online))

    def disconnect(self, uuid):
        """Отключает контакт."""
        with self.lock:
            if uuid in self.connections:
                try:
                    self.connections[uuid].send(make_bye())
                except Exception:
                    pass
                self.connections[uuid].close()
                del self.connections[uuid]

    def is_contact_online(self, uuid):
        """Проверяет, подключён ли контакт."""
        if not self.server:
            return False
        return self.server.get_client_by_uuid(uuid) is not None

    def shutdown(self):
        """Останавливает транспорт."""
        if self.server:
            self.server.stop()
        with self.lock:
            for ts in self.connections.values():
                try:
                    ts.close()
                except Exception:
                    pass
            self.connections = {}