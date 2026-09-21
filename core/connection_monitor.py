import threading
import time
from datetime import datetime


class ConnectionMonitor:
    """
    Мониторит состояние всех соединений.
    Уведомляет UI об изменениях.
    """

    def __init__(self, transport):
        self.transport = transport
        self.connections = {}  # uuid -> info
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

        self.on_connect = None
        self.on_disconnect = None
        self.on_unstable = None

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
                self._check_connections()
            except Exception:
                pass
            time.sleep(5)

    def _check_connections(self):
        """Проверяет состояние соединений."""
        if not self.transport:
            return

        current_online = set()

        if self.transport.server:
            for client_id in self.transport.server.list_clients():
                with self.transport.server.lock:
                    client = self.transport.server.clients.get(client_id, {})
                    uuid = client.get("uuid")

                if uuid:
                    current_online.add(uuid)

        with self.lock:
            previously_online = set(self.connections.keys())

            # новые подключения
            for uuid in current_online - previously_online:
                self.connections[uuid] = {
                    "connected_at": datetime.now(),
                    "status": "online",
                }
                if self.on_connect:
                    try:
                        self.on_connect(uuid)
                    except Exception:
                        pass

            # отключения
            for uuid in previously_online - current_online:
                del self.connections[uuid]
                if self.on_disconnect:
                    try:
                        self.on_disconnect(uuid)
                    except Exception:
                        pass

    def is_online(self, uuid):
        with self.lock:
            return uuid in self.connections

    def get_uptime(self, uuid):
        """Время в сети."""
        with self.lock:
            info = self.connections.get(uuid)
            if not info:
                return None
            return (datetime.now() - info["connected_at"]).total_seconds()

    def list_online(self):
        with self.lock:
            return list(self.connections.keys())