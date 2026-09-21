import os
import io
import time
import base64
import hashlib
import secrets
from pathlib import Path
from datetime import datetime

from core.crypto import encrypt_bytes, decrypt_bytes


CHUNK_SIZE = 32 * 1024  # 32 KB
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

FILES_DIR = Path.home() / ".nocturne" / "files"


class FileTransfer:
    """Отправка/приём файлов через NOCTURNE."""

    def __init__(self, file_id, filename, size, total_chunks, direction):
        self.file_id = file_id
        self.filename = filename
        self.size = size
        self.total_chunks = total_chunks
        self.direction = direction  # "out" / "in"
        self.chunks = {}  # index -> bytes
        self.received_chunks = 0
        self.started = datetime.now()
        self.finished = None
        self.sha256 = None

    def add_chunk(self, index, data):
        self.chunks[index] = data
        self.received_chunks += 1

    def is_complete(self):
        return self.received_chunks == self.total_chunks

    def get_data(self):
        if not self.is_complete():
            return None
        result = b""
        for i in range(self.total_chunks):
            result += self.chunks.get(i, b"")
        return result

    def progress(self):
        if self.total_chunks == 0:
            return 0.0
        return self.received_chunks / self.total_chunks * 100


class FileManager:
    """Менеджер файловых передач."""

    def __init__(self, shared_key_getter):
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        self.transfers = {}  # file_id -> FileTransfer
        self.shared_key_getter = shared_key_getter

    def prepare_outgoing(self, file_path, uuid):
        """
        Готовит файл к отправке.
        Возвращает (transfer, packets_list) или (None, error).
        """
        from core.protocol import (
            make_file_start, make_file_chunk, make_file_end,
        )

        path = Path(file_path)

        if not path.exists() or not path.is_file():
            return None, "Файл не найден"

        size = path.stat().st_size

        if size > MAX_FILE_SIZE:
            return None, f"Файл слишком большой (макс. {MAX_FILE_SIZE // 1024 // 1024} MB)"

        filename = path.name
        file_id = f"file-{secrets.token_hex(8)}"

        shared_key = self.shared_key_getter(uuid)
        if not shared_key:
            return None, "Нет общего ключа с контактом"

        # читаем файл
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return None, str(e)

        file_sha = hashlib.sha256(raw).hexdigest()

        # шифруем весь файл
        encrypted = encrypt_bytes(shared_key, raw)

        # разбиваем на чанки
        chunks = []
        total_chunks = (len(encrypted) + CHUNK_SIZE - 1) // CHUNK_SIZE

        for i in range(total_chunks):
            start = i * CHUNK_SIZE
            end = start + CHUNK_SIZE
            chunk = encrypted[start:end]
            chunks.append(chunk)

        transfer = FileTransfer(
            file_id, filename, size, total_chunks, "out"
        )
        transfer.sha256 = file_sha

        self.transfers[file_id] = transfer

        # собираем пакеты
        packets = []

        packets.append(make_file_start(
            file_id, filename, size, total_chunks,
        ))

        for i, chunk in enumerate(chunks):
            chunk_b64 = base64.b64encode(chunk).decode("ascii")
            packets.append(make_file_chunk(file_id, i, chunk_b64))

        packets.append(make_file_end(file_id, file_sha))

        return transfer, packets

    def handle_file_start(self, payload, sender_uuid):
        """Обработка входящего FILE_START."""
        try:
            file_id = payload["file_id"]
            filename = payload["filename"]
            size = payload["size"]
            total_chunks = payload["total_chunks"]

            transfer = FileTransfer(
                file_id, filename, size, total_chunks, "in"
            )
            self.transfers[file_id] = transfer

            return transfer, None
        except Exception as e:
            return None, str(e)

    def handle_file_chunk(self, payload, sender_uuid):
        """Обработка входящего FILE_CHUNK."""
        try:
            file_id = payload["file_id"]
            index = payload["index"]
            data_b64 = payload["data"]

            transfer = self.transfers.get(file_id)
            if not transfer:
                return False, "Неизвестный file_id"

            chunk = base64.b64decode(data_b64)
            transfer.add_chunk(index, chunk)

            return True, None
        except Exception as e:
            return False, str(e)

    def handle_file_end(self, payload, sender_uuid):
        """Обработка FILE_END — расшифровка и сохранение."""
        try:
            file_id = payload["file_id"]
            expected_sha = payload.get("sha256")

            transfer = self.transfers.get(file_id)
            if not transfer:
                return None, "Неизвестный file_id"

            if not transfer.is_complete():
                return None, "Не все чанки получены"

            encrypted = transfer.get_data()
            if not encrypted:
                return None, "Ошибка сбора данных"

            shared_key = self.shared_key_getter(sender_uuid)
            if not shared_key:
                return None, "Нет общего ключа"

            decrypted = decrypt_bytes(shared_key, encrypted)
            if decrypted is None:
                return None, "Ошибка расшифровки"

            # проверка sha256
            actual_sha = hashlib.sha256(decrypted).hexdigest()
            if expected_sha and actual_sha != expected_sha:
                return None, "Хэш не совпадает — файл повреждён"

            # сохраняем
            save_dir = FILES_DIR / sender_uuid[:16]
            save_dir.mkdir(parents=True, exist_ok=True)

            save_path = save_dir / transfer.filename

            # избегаем перезаписи
            counter = 1
            while save_path.exists():
                stem = Path(transfer.filename).stem
                suffix = Path(transfer.filename).suffix
                save_path = save_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            with open(save_path, "wb") as f:
                f.write(decrypted)

            transfer.finished = datetime.now()

            return save_path, None
        except Exception as e:
            return None, str(e)

    def get_transfer(self, file_id):
        return self.transfers.get(file_id)

    def cancel(self, file_id):
        if file_id in self.transfers:
            del self.transfers[file_id]
            return True
        return False