import os
import sys
import time
import socket
import subprocess
import shutil
from pathlib import Path

try:
    from stem.control import Controller
    from stem.process import launch_tor_with_config
    HAS_STEM = True
except ImportError:
    HAS_STEM = False


class TorManager:
    """Управление Tor: запуск процесса, создание .onion-сервиса."""

    def __init__(self, data_dir=None, tor_binary=None):
        self.data_dir = Path(data_dir) if data_dir else Path("tor/data")
        self.tor_binary = tor_binary or self._find_tor_binary()
        self.process = None
        self.controller = None
        self.onion_hostname = None
        self.onion_private_key = None
        self.socks_port = 9050
        self.control_port = 9051
        self.hidden_service_dir = self.data_dir / "hidden_service"

    def _find_tor_binary(self):
        """Ищет tor.exe в системе."""
        candidates = [
            Path("tor/tor.exe"),
            Path("tor/tor"),
            Path("tor/Tor/tor.exe"),
        ]

        for c in candidates:
            if c.exists():
                return str(c)

        system_tor = shutil.which("tor")
        if system_tor:
            return system_tor

        return None

    def is_available(self):
        return self.tor_binary is not None

    def start(self, timeout=60):
        """Запускает Tor-процесс."""
        if not HAS_STEM:
            return False, "Не установлен stem. pip install stem"

        if not self.tor_binary:
            return False, (
                "Не найден tor.exe.\n"
                "Скачай Tor Expert Bundle:\n"
                "https://www.torproject.org/download/tor/\n"
                "и распакуй в папку tor/"
            )

        if self.process:
            return True, "Уже запущен"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.hidden_service_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.process = subprocess.Popen(
                [
                    self.tor_binary,
                    "--SocksPort", str(self.socks_port),
                    "--ControlPort", str(self.control_port),
                    "--DataDirectory", str(self.data_dir / "main"),
                    "--CookieAuthentication", "0",
                    "--Log", "notice stdout",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as e:
            return False, f"Не удалось запустить Tor: {e}"

        if not self._wait_for_bootstrap(timeout):
            self.stop()
            return False, "Tor не запустился за отведённое время"

        return True, None

    def _wait_for_bootstrap(self, timeout=60):
        """Ждёт готовности Tor."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(("127.0.0.1", self.socks_port), timeout=2):
                    return True
            except Exception:
                time.sleep(1)
        return False

    def create_hidden_service(self, port):
        """Создаёт .onion-сервис на указанном порту. Возвращает hostname."""
        if not HAS_STEM:
            return None, "Не установлен stem"

        try:
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()

                response = controller.create_ephemeral_hidden_service(
                    {port: port},
                    await_publication=True,
                )

                self.onion_hostname = response.service_id + ".onion"
                self.onion_private_key = response.private_key

                return self.onion_hostname, None
        except Exception as e:
            return None, f"Ошибка создания onion-сервиса: {e}"

    def get_onion_address(self):
        return self.onion_hostname

    def stop(self):
        """Останавливает Tor."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def is_running(self):
        return self.process is not None and self.process.poll() is None