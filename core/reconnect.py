import time
import threading
from datetime import datetime, timedelta


class ReconnectManager:
    """
    Автоматическое переподключение к контактам.
    Периодически проверяет, какие контакты offline,
    и пытается к ним подключиться.
    """

    def __init__(self, transport, contact_getter, interval=60):
        self.transport = transport
        self.get_contacts = contact_getter
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None

        # uuid -> последняя попытка
        self.last_attempts = {}
        # uuid -> число неудачных попыток
        self.failures = {}
        # uuid -> next_retry_at (exponential backoff)
        self.next_retry = {}

        self.max_backoff_minutes = 30

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
                self._reconnect_all()
            except Exception:
                pass

            for _ in range(self.interval):
                if self._stop.is_set():
                    break
                time.sleep(1)

    def _reconnect_all(self):
        if not self.transport:
            return

        contacts = self.get_contacts()
        now = datetime.now()

        for contact in contacts:
            uuid = contact.get("uuid")
            onion = contact.get("onion_address")

            if not uuid or not onion:
                continue

            # уже подключён
            if self.transport.is_contact_online(uuid):
                self.failures[uuid] = 0
                continue

            # проверяем backoff
            next_retry = self.next_retry.get(uuid)
            if next_retry and now < next_retry:
                continue

            # пытаемся подключиться
            self._attempt_reconnect(uuid, onion)

    def _attempt_reconnect(self, uuid, onion):
        """Попытка переподключения."""
        try:
            success, error = self.transport.connect_to(onion, timeout=30)

            if success:
                self.failures[uuid] = 0
                self.next_retry.pop(uuid, None)
            else:
                self._register_failure(uuid)
        except Exception:
            self._register_failure(uuid)

    def _register_failure(self, uuid):
        """Регистрирует неудачную попытку с exponential backoff."""
        attempts = self.failures.get(uuid, 0) + 1
        self.failures[uuid] = attempts

        # exponential backoff: 1, 2, 4, 8, 16, 30 минут
        minutes = min(2 ** (attempts - 1), self.max_backoff_minutes)
        self.next_retry[uuid] = datetime.now() + timedelta(minutes=minutes)

    def force_reconnect(self, uuid):
        """Принудительное переподключение."""
        self.next_retry.pop(uuid, None)
        contacts = self.get_contacts()

        for c in contacts:
            if c.get("uuid") == uuid:
                onion = c.get("onion_address")
                if onion:
                    self._attempt_reconnect(uuid, onion)
                break

    def get_status(self):
        """Возвращает текущий статус попыток."""
        return {
            uuid: {
                "failures": self.failures.get(uuid, 0),
                "next_retry": self.next_retry.get(uuid, {}).isoformat()
                if uuid in self.next_retry else None,
            }
            for uuid in self.failures
        }


class HeartbeatManager:
    """
    Heartbeat — периодически отправляет PING контактам
    для проверки живости соединения.
    """

    def __init__(self, transport, interval=30, timeout=10):
        self.transport = transport
        self.interval = interval
        self.timeout = timeout
        self._stop = threading.Event()
        self._thread = None

        # uuid -> последний PONG
        self.last_pongs = {}

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
        from core.protocol import make_ping

        while not self._stop.is_set():
            try:
                if self.transport and self.transport.server:
                    for client_id in self.transport.server.list_clients():
                        self.transport.server.send_to(
                            client_id, make_ping()
                        )
            except Exception:
                pass

            for _ in range(self.interval):
                if self._stop.is_set():
                    break
                time.sleep(1)

    def register_pong(self, uuid):
        """Регистрирует получение PONG."""
        self.last_pongs[uuid] = datetime.now()

    def is_alive(self, uuid):
        """Проверяет, отвечает ли контакт."""
        last = self.last_pongs.get(uuid)
        if not last:
            return False

        elapsed = (datetime.now() - last).total_seconds()
        return elapsed < (self.interval * 2 + self.timeout)