import sys
import os
from pathlib import Path


class NotificationManager:
    """Системные уведомления (Windows / Linux / macOS)."""

    def __init__(self, app_name="NOCTURNE"):
        self.app_name = app_name
        self.enabled = True
        self.tray_icon = None

    def set_tray(self, tray_icon):
        """Привязка к иконке в трее."""
        self.tray_icon = tray_icon

    def notify(self, title, message, timeout=5):
        """Показывает уведомление."""
        if not self.enabled:
            return False

        # через трей (лучше всего)
        if self.tray_icon:
            try:
                from PyQt6.QtWidgets import QSystemTrayIcon
                self.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    timeout * 1000,
                )
                return True
            except Exception:
                pass

        # fallback — через систему
        return self._system_notify(title, message)

    def _system_notify(self, title, message):
        if os.name == "nt":
            return self._windows_notify(title, message)
        elif sys.platform == "darwin":
            return self._macos_notify(title, message)
        else:
            return self._linux_notify(title, message)

    def _windows_notify(self, title, message):
        """Windows 10+ уведомления через win10toast / plyer."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                duration=5,
                threaded=True,
            )
            return True
        except ImportError:
            pass
        except Exception:
            pass

        # fallback — просто консоль
        print(f"[NOTIFY] {title}: {message}")
        return False

    def _macos_notify(self, title, message):
        try:
            import subprocess
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                timeout=3,
            )
            return True
        except Exception:
            return False

    def _linux_notify(self, title, message):
        try:
            import subprocess
            subprocess.run(
                ["notify-send", title, message],
                timeout=3,
            )
            return True
        except Exception:
            return False

    def notify_message(self, sender_name, text):
        """Уведомление о новом сообщении."""
        text_preview = text[:80] + ("..." if len(text) > 80 else "")
        return self.notify(
            f"🦇 {sender_name}",
            text_preview,
        )

    def notify_file(self, sender_name, filename, size):
        """Уведомление о новом файле."""
        return self.notify(
            f"🦇 {sender_name}",
            f"📎 Получен файл: {filename} ({self._human_size(size)})",
        )

    def notify_connection(self, nickname, online):
        """Уведомление о подключении/отключении."""
        status = "онлайн" if online else "офлайн"
        return self.notify(
            "🦇 NOCTURNE",
            f"{nickname} теперь {status}",
        )

    @staticmethod
    def _human_size(n):
        for unit in ("B", "KB", "MB", "GB"):
            if abs(n) < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    def toggle(self, enabled):
        self.enabled = enabled
        return self.enabled