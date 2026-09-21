import json
import time
import threading
import secrets
from pathlib import Path
from datetime import datetime
from collections import defaultdict


QUEUE_DIR = Path.home() / ".nocturne"
QUEUE_FILE = QUEUE_DIR / "message_queue.json"


class MessageQueue:
    """
    Очередь исходящих сообщений.
    Хранит сообщения, которые не удалось доставить
    (контакт offline), и отправляет при подключении.
    """

    def __init__(self, encryption_key=None):
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        self.encryption_key = encryption_key
        self.queues = defaultdict(list)  # uuid -> [messages]
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if not QUEUE_FILE.exists():
            return

        try:
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            for uuid, messages in data.get("queues", {}).items():
                self.queues[uuid] = messages
        except Exception:
            pass

    def _save(self):
        try:
            data = {
                "queues": dict(self.queues),
                "saved": datetime.now().isoformat(),
            }
            QUEUE_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def enqueue(self, uuid, msg_type, payload, priority=0):
        """
        Добавляет сообщение в очередь.
        Возвращает queue_id.
        """
        queue_id = f"q-{secrets.token_hex(8)}"

        message = {
            "id": queue_id,
            "type": msg_type,
            "payload": payload,
            "priority": priority,
            "created": datetime.now().isoformat(),
            "attempts": 0,
            "last_attempt": None,
        }

        with self.lock:
            self.queues[uuid].append(message)
            # сортируем по приоритету
            self.queues[uuid].sort(
                key=lambda m: (-m["priority"], m["created"])
            )
            self._save()

        return queue_id

    def dequeue(self, uuid):
        """Достаёт следующее сообщение из очереди."""
        with self.lock:
            queue = self.queues.get(uuid, [])
            if not queue:
                return None

            message = queue.pop(0)
            self._save()
            return message

    def peek(self, uuid, limit=10):
        """Смотрит очередь без извлечения."""
        with self.lock:
            return list(self.queues.get(uuid, []))[:limit]

    def size(self, uuid=None):
        """Размер очереди (для одного или всех)."""
        with self.lock:
            if uuid:
                return len(self.queues.get(uuid, []))
            return sum(len(q) for q in self.queues.values())

    def clear(self, uuid=None):
        """Очищает очередь."""
        with self.lock:
            if uuid:
                self.queues.pop(uuid, None)
            else:
                self.queues.clear()
            self._save()

    def register_attempt(self, uuid, message_id, success):
        """Регистрирует попытку отправки."""
        with self.lock:
            queue = self.queues.get(uuid, [])
            for m in queue:
                if m["id"] == message_id:
                    m["attempts"] += 1
                    m["last_attempt"] = datetime.now().isoformat()
                    if not success:
                        # сдвигаем в конец
                        queue.remove(m)
                        queue.append(m)
                    break
            self._save()

    def get_all_uuids(self):
        """Все UUID с непустыми очередями."""
        with self.lock:
            return [u for u, q in self.queues.items() if q]

    def drop_old(self, max_age_hours=72):
        """Удаляет старые сообщения из очереди."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        with self.lock:
            for uuid in list(self.queues.keys()):
                self.queues[uuid] = [
                    m for m in self.queues[uuid]
                    if datetime.fromisoformat(m["created"]) > cutoff
                ]
                if not self.queues[uuid]:
                    del self.queues[uuid]
            self._save()


class DeliveryTracker:
    """
    Отслеживание доставки сообщений.
    Хранит статусы: queued / sent / delivered / read / failed.
    """

    def __init__(self):
        self.statuses = {}  # msg_id -> статус
        self.lock = threading.Lock()

    def set_status(self, msg_id, status):
        with self.lock:
            self.statuses[msg_id] = {
                "status": status,
                "time": datetime.now().isoformat(),
            }

    def get_status(self, msg_id):
        with self.lock:
            return self.statuses.get(msg_id)

    def mark_queued(self, msg_id):
        self.set_status(msg_id, "queued")

    def mark_sent(self, msg_id):
        self.set_status(msg_id, "sent")

    def mark_delivered(self, msg_id):
        self.set_status(msg_id, "delivered")

    def mark_read(self, msg_id):
        self.set_status(msg_id, "read")

    def mark_failed(self, msg_id, reason=""):
        self.set_status(msg_id, "failed")
        with self.lock:
            if msg_id in self.statuses:
                self.statuses[msg_id]["reason"] = reason


class QueueProcessor:
    """
    Обработчик очереди — периодически пытается
    отправить накопившиеся сообщения.
    """

    def __init__(self, queue, transport, interval=30):
        self.queue = queue
        self.transport = transport
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.delivery_tracker = DeliveryTracker()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._process_once()
            except Exception:
                pass

            for _ in range(self.interval):
                if self._stop.is_set():
                    break
                time.sleep(1)

    def _process_once(self):
        """Одна итерация обработки."""
        for uuid in self.queue.get_all_uuids():
            if not self.transport:
                continue

            if not self.transport.is_contact_online(uuid):
                continue

            # отправляем до 20 сообщений за раз
            for _ in range(20):
                message = self.queue.dequeue(uuid)
                if not message:
                    break

                try:
                    payload = message["payload"]
                    # пробуем отправить через транспорт
                    success = self.transport.send_raw(uuid, payload)

                    if success:
                        self.delivery_tracker.mark_sent(message["id"])
                    else:
                        # возвращаем в очередь
                        self.queue.enqueue(
                            uuid,
                            message["type"],
                            payload,
                            priority=message.get("priority", 0),
                        )
                        break
                except Exception:
                    break