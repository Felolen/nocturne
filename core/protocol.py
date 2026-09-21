import json
import base64
import struct
from datetime import datetime


PROTOCOL_VERSION = 1
MAGIC = b"NOCT"


# ═══════════════════════════════════════════════════════════
# ФОРМАТ ПАКЕТА
# ═══════════════════════════════════════════════════════════
#
# [MAGIC (4 байта)] [VERSION (1 байт)] [TYPE (1 байт)]
# [LENGTH (4 байта, big endian)] [PAYLOAD (JSON, utf-8)]
#
# Итого заголовок: 10 байт

HEADER_SIZE = 10


# ─── Типы сообщений ───
class MessageType:
    HELLO = 1              # приветствие при соединении
    HANDSHAKE = 2          # обмен публичными ключами
    TEXT = 3               # текстовое сообщение
    ACK = 4                # подтверждение
    PING = 5               # проверка связи
    PONG = 6               # ответ на ping
    KEY_EXCHANGE = 7       # обмен ключами
    CONTACT_REQUEST = 8    # запрос на добавление в контакты
    CONTACT_ACCEPT = 9     # принятие контакта
    FILE = 10              # файл (на будущее)
    TYPING = 11            # печатает...
    ONLINE = 12            # online-статус
    BYE = 13               # прощание


def pack_message(msg_type, payload):
    """Упаковывает сообщение в байты."""
    if isinstance(payload, dict):
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    elif isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload

    header = (
        MAGIC
        + bytes([PROTOCOL_VERSION])
        + bytes([msg_type])
        + struct.pack(">I", len(payload_bytes))
    )

    return header + payload_bytes


def unpack_message(data):
    """Распаковывает сообщение. Возвращает (type, payload) или (None, error)."""
    if len(data) < HEADER_SIZE:
        return None, "Слишком короткий пакет"

    if data[:4] != MAGIC:
        return None, "Неверная сигнатура"

    version = data[4]
    if version != PROTOCOL_VERSION:
        return None, f"Несовместимая версия: {version}"

    msg_type = data[5]
    length = struct.unpack(">I", data[6:10])[0]

    if len(data) < HEADER_SIZE + length:
        return None, "Неполный пакет"

    payload_bytes = data[HEADER_SIZE:HEADER_SIZE + length]

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        payload = payload_bytes

    return (msg_type, payload), None


# ═══════════════════════════════════════════════════════════
# КОНСТРУКТОРЫ СООБЩЕНИЙ
# ═══════════════════════════════════════════════════════════

def make_hello(identity):
    """Приветствие при подключении."""
    return pack_message(MessageType.HELLO, {
        "uuid": identity.uuid,
        "fingerprint": identity.fingerprint,
        "nickname": identity.nickname,
        "version": PROTOCOL_VERSION,
    })


def make_handshake(identity):
    """Обмен публичными ключами."""
    return pack_message(MessageType.HANDSHAKE, {
        "uuid": identity.uuid,
        "public_key_hex": identity.public_bytes.hex(),
        "fingerprint": identity.fingerprint,
        "nickname": identity.nickname,
        "onion": identity.onion_address,
    })


def make_text(encrypted_data, msg_id=None):
    """Зашифрованное текстовое сообщение."""
    return pack_message(MessageType.TEXT, {
        "id": msg_id or f"msg-{datetime.now().timestamp()}",
        "data": encrypted_data,
        "time": datetime.now().isoformat(),
    })


def make_ack(msg_id):
    """Подтверждение получения."""
    return pack_message(MessageType.ACK, {"id": msg_id})


def make_ping():
    return pack_message(MessageType.PING, {"time": datetime.now().isoformat()})


def make_pong():
    return pack_message(MessageType.PONG, {"time": datetime.now().isoformat()})


def make_bye(reason="user closed"):
    return pack_message(MessageType.BYE, {"reason": reason})


def make_typing(is_typing=True):
    return pack_message(MessageType.TYPING, {"typing": is_typing})


def make_online(status=True):
    return pack_message(MessageType.ONLINE, {"online": status})


# ═══════════════════════════════════════════════════════════
# ОБРАБОТКА ВХОДЯЩИХ
# ═══════════════════════════════════════════════════════════

def handle_message(data):
    """
    Обрабатывает входящий пакет.
    Возвращает dict с полями: type, payload, error.
    """
    result, error = unpack_message(data)

    if error:
        return {"error": error}

    msg_type, payload = result

    return {
        "type": msg_type,
        "payload": payload,
        "error": None,
    }


def get_message_name(msg_type):
    """Читаемое имя типа сообщения."""
    names = {
        MessageType.HELLO: "HELLO",
        MessageType.HANDSHAKE: "HANDSHAKE",
        MessageType.TEXT: "TEXT",
        MessageType.ACK: "ACK",
        MessageType.PING: "PING",
        MessageType.PONG: "PONG",
        MessageType.KEY_EXCHANGE: "KEY_EXCHANGE",
        MessageType.CONTACT_REQUEST: "CONTACT_REQUEST",
        MessageType.CONTACT_ACCEPT: "CONTACT_ACCEPT",
        MessageType.FILE: "FILE",
        MessageType.TYPING: "TYPING",
        MessageType.ONLINE: "ONLINE",
        MessageType.BYE: "BYE",
    }
    return names.get(msg_type, f"UNKNOWN({msg_type})")