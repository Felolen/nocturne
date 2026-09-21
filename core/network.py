import socket
import socks
import threading
import time
from datetime import datetime


SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 9050


class TorSocket:
    """
    TCP-сокет через Tor SOCKS5-прокси.
    """

    def __init__(self, socks_host=SOCKS_HOST, socks_port=SOCKS_PORT):
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.sock = None

    def connect(self, onion_address, port=9999, timeout=60):
        """
        Подключается к .onion-адресу через Tor.
        Возвращает True или (False, error).
        """
        if not onion_address.endswith(".onion"):
            onion_address = onion_address + ".onion"

        try:
            s = socks.socksocket()
            s.set_proxy(
                socks.SOCKS5,
                self.socks_host,
                self.socks_port,
                rdns=True,
            )
            s.settimeout(timeout)
            s.connect((onion_address, port))

            self.sock = s
            return True, None
        except socks.ProxyConnectionError as e:
            return False, f"Tor не запущен: {e}"
        except socks.GeneralProxyError as e:
            return False, f"Ошибка прокси: {e}"
        except socket.timeout:
            return False, "Таймаут подключения"
        except Exception as e:
            return False, str(e)

    def send(self, data):
        if not self.sock:
            return False, "Нет соединения"

        try:
            self.sock.sendall(data)
            return True, None
        except Exception as e:
            return False, str(e)

    def recv(self, buffer_size=4096):
        if not self.sock:
            return None

        try:
            return self.sock.recv(buffer_size)
        except Exception:
            return None

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def is_connected(self):
        return self.sock is not None


class TorServer:
    """
    TCP-сервер, слушающий на локальном порту.
    Tor перенаправляет трафик с .onion-адреса на этот порт.
    """

    def __init__(self, port=9999):
        self.port = port
        self.server_sock = None
        self.running = False
        self.thread = None
        self.clients = {}
        self.on_new_connection = None
        self.on_message = None
        self.on_disconnect = None
        self.lock = threading.Lock()

    def start(self):
        """Запускает сервер."""
        if self.running:
            return False, "Уже запущен"

        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("127.0.0.1", self.port))
            self.server_sock.listen(10)

            self.running = True
            self.thread = threading.Thread(target=self._accept_loop, daemon=True)
            self.thread.start()

            return True, None
        except Exception as e:
            return False, str(e)

    def _accept_loop(self):
        """Принимает входящие соединения."""
        while self.running:
            try:
                self.server_sock.settimeout(1.0)
                client_sock, addr = self.server_sock.accept()

                client_id = f"{addr[0]}:{addr[1]}:{time.time()}"

                with self.lock:
                    self.clients[client_id] = {
                        "sock": client_sock,
                        "addr": addr,
                        "connected_at": datetime.now(),
                        "uuid": None,
                    }

                if self.on_new_connection:
                    try:
                        self.on_new_connection(client_id)
                    except Exception:
                        pass

                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_id, client_sock),
                    daemon=True,
                )
                thread.start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, client_id, sock):
        """Обрабатывает сообщения от клиента."""
        sock.settimeout(1.0)

        while self.running:
            try:
                data = sock.recv(4096)
                if not data:
                    break

                if self.on_message:
                    try:
                        self.on_message(client_id, data)
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except Exception:
                break

        # отключение
        with self.lock:
            if client_id in self.clients:
                del self.clients[client_id]

        if self.on_disconnect:
            try:
                self.on_disconnect(client_id)
            except Exception:
                pass

        try:
            sock.close()
        except Exception:
            pass

    def send_to(self, client_id, data):
        """Отправляет данные конкретному клиенту."""
        with self.lock:
            client = self.clients.get(client_id)

        if not client:
            return False, "Клиент не найден"

        try:
            client["sock"].sendall(data)
            return True, None
        except Exception as e:
            return False, str(e)

    def broadcast(self, data, exclude=None):
        """Отправляет всем клиентам."""
        with self.lock:
            clients = list(self.clients.items())

        for client_id, client in clients:
            if exclude and client_id == exclude:
                continue
            try:
                client["sock"].sendall(data)
            except Exception:
                pass

    def set_client_uuid(self, client_id, uuid):
        """Привязывает UUID к соединению."""
        with self.lock:
            if client_id in self.clients:
                self.clients[client_id]["uuid"] = uuid

    def get_client_by_uuid(self, uuid):
        """Ищет клиента по UUID."""
        with self.lock:
            for client_id, client in self.clients.items():
                if client.get("uuid") == uuid:
                    return client_id
            return None

    def list_clients(self):
        """Список активных клиентов."""
        with self.lock:
            return list(self.clients.keys())

    def get_client_count(self):
        with self.lock:
            return len(self.clients)

    def stop(self):
        """Останавливает сервер."""
        self.running = False

        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

        with self.lock:
            for client_id, client in self.clients.items():
                try:
                    client["sock"].close()
                except Exception:
                    pass
            self.clients = {}


def test_tor_connection():
    """Проверяет, доступен ли Tor SOCKS-прокси."""
    try:
        with socket.create_connection((SOCKS_HOST, SOCKS_PORT), timeout=3):
            return True
    except Exception:
        return False