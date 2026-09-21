import json
import base64
import struct
from datetime import datetime


PROTOCOL_VERSION = 2
MAGIC = b"NOCT"

HEADER_SIZE = 10


class MessageType:
    # базовые
    HELLO = 1
    HANDSHAKE = 2
    TEXT = 3
    ACK = 4
    PING = 5
    PONG = 6
    BYE = 13

    # контакты
    CONTACT_REQUEST = 8
    CONTACT_ACCEPT = 9
    CONTACT_BLOCK = 14

    # файлы
    FILE_START = 20
    FILE_CHUNK = 21
    FILE_END = 22
    FILE_ACCEPT = 23
    FILE_REJECT = 24

    # группы
    GROUP_CREATE = 30
    GROUP_INVITE = 31
    GROUP_JOIN = 32
    GROUP_LEAVE = 33
    GROUP_MESSAGE = 34
    GROUP_INFO = 35

    # UX
    TYPING = 11
    ONLINE = 12
    READ = 40
    EDIT = 41
    DELETE = 42

    # безопасность
    FINGERPRINT_VERIFY = 50

    # очередь
    QUEUED = 60
    DELIVERY = 61


def pack_message(msg_type, payload):
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
# КОНСТРУКТОРЫ
# ═══════════════════════════════════════════════════════════

def make_hello(identity):
    return pack_message(MessageType.HELLO, {
        "uuid": identity.uuid,
        "fingerprint": identity.fingerprint,
        "nickname": identity.nickname,
        "version": PROTOCOL_VERSION,
    })


def make_handshake(identity):
    return pack_message(MessageType.HANDSHAKE, {
        "uuid": identity.uuid,
        "public_key_hex": identity.public_bytes.hex(),
        "fingerprint": identity.fingerprint,
        "nickname": identity.nickname,
        "onion": identity.onion_address,
    })


def make_text(encrypted_data, msg_id=None, reply_to=None):
    return pack_message(MessageType.TEXT, {
        "id": msg_id or f"msg-{datetime.now().timestamp()}",
        "data": encrypted_data,
        "time": datetime.now().isoformat(),
        "reply_to": reply_to,
    })


def make_ack(msg_id):
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


def make_read(msg_id):
    return pack_message(MessageType.READ, {"id": msg_id})


def make_edit(msg_id, new_encrypted):
    return pack_message(MessageType.EDIT, {
        "id": msg_id,
        "data": new_encrypted,
        "time": datetime.now().isoformat(),
    })


def make_delete(msg_id):
    return pack_message(MessageType.DELETE, {"id": msg_id})


# ─── Файлы ───

def make_file_start(file_id, filename, size, total_chunks, encrypted_key=None):
    return pack_message(MessageType.FILE_START, {
        "file_id": file_id,
        "filename": filename,
        "size": size,
        "total_chunks": total_chunks,
        "encrypted_key": encrypted_key,
        "time": datetime.now().isoformat(),
    })


def make_file_chunk(file_id, chunk_index, encrypted_data):
    return pack_message(MessageType.FILE_CHUNK, {
        "file_id": file_id,
        "index": chunk_index,
        "data": encrypted_data,
    })


def make_file_end(file_id, sha256_hash):
    return pack_message(MessageType.FILE_END, {
        "file_id": file_id,
        "sha256": sha256_hash,
    })


def make_file_accept(file_id):
    return pack_message(MessageType.FILE_ACCEPT, {"file_id": file_id})


def make_file_reject(file_id, reason=""):
    return pack_message(MessageType.FILE_REJECT, {
        "file_id": file_id,
        "reason": reason,
    })


# ─── Группы ───

def make_group_create(group_id, name, members):
    return pack_message(MessageType.GROUP_CREATE, {
        "group_id": group_id,
        "name": name,
        "members": members,
        "time": datetime.now().isoformat(),
    })


def make_group_invite(group_id, name, inviter_uuid, inviter_nickname):
    return pack_message(MessageType.GROUP_INVITE, {
        "group_id": group_id,
        "name": name,
        "inviter_uuid": inviter_uuid,
        "inviter_nickname": inviter_nickname,
    })


def make_group_join(group_id, uuid, nickname):
    return pack_message(MessageType.GROUP_JOIN, {
        "group_id": group_id,
        "uuid": uuid,
        "nickname": nickname,
    })


def make_group_leave(group_id, uuid):
    return pack_message(MessageType.GROUP_LEAVE, {
        "group_id": group_id,
        "uuid": uuid,
    })


def make_group_message(group_id, encrypted_data, msg_id=None, sender_uuid=None):
    return pack_message(MessageType.GROUP_MESSAGE, {
        "group_id": group_id,
        "id": msg_id or f"gmsg-{datetime.now().timestamp()}",
        "data": encrypted_data,
        "sender": sender_uuid,
        "time": datetime.now().isoformat(),
    })


def make_group_info(group_id, name, members):
    return pack_message(MessageType.GROUP_INFO, {
        "group_id": group_id,
        "name": name,
        "members": members,
    })


# ─── Безопасность ───

def make_fingerprint_verify(uuid, fingerprint):
    return pack_message(MessageType.FINGERPRINT_VERIFY, {
        "uuid": uuid,
        "fingerprint": fingerprint,
        "time": datetime.now().isoformat(),
    })


def make_block(reason=""):
    return pack_message(MessageType.CONTACT_BLOCK, {"reason": reason})


def get_message_name(msg_type):
    names = {v: k for k, v in vars(MessageType).items() if not k.startswith("_")}
    return names.get(msg_type, f"UNKNOWN({msg_type})")


def handle_message(data):
    result, error = unpack_message(data)
    if error:
        return {"error": error}
    msg_type, payload = result
    return {"type": msg_type, "payload": payload, "error": None}