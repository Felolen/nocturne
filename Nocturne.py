#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🦇 NOCTURNE v0.2 — анонимный P2P-мессенджер через Tor.

Шифрование: X25519 + AES-256-GCM
Транспорт: Tor Hidden Services (.onion)
Файлы · Группы · Очередь · Уведомления

Зависимости:  pip install PyQt6 cryptography stem pysocks requests colorama
Запуск:       python Nocturne.py
"""

import os
import sys
import time
import hashlib
import threading
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ═══════════════════════════════════════════════════════════
# ЗАВИСИМОСТИ
# ═══════════════════════════════════════════════════════════

try:
    from PyQt6.QtWidgets import (
        QApplication, QMessageBox, QDialog,
        QSplashScreen, QInputDialog,
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor
except ImportError:
    print("Установите: pip install PyQt6 cryptography stem pysocks")
    sys.exit(1)

try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey  # noqa: F401
except ImportError:
    print("Установите: pip install cryptography")
    sys.exit(1)

try:
    import socks  # noqa: F401
except ImportError:
    print("Установите: pip install pysocks")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════
# НАШИ МОДУЛИ
# ═══════════════════════════════════════════════════════════

from core.identity import Identity, IDENTITY_FILE
from core.storage import MessageStore, ContactStore, Settings
from core.tor_manager import TorManager
from core.network import TorServer, test_tor_connection
from core.transport import Transport
from core.crypto import derive_shared_key, encrypt_bytes, decrypt_bytes, fingerprint
from core.queue import MessageQueue, QueueProcessor
from core.files import FileManager
from core.groups import GroupManager
from core.notifications import NotificationManager
from core.sounds import SoundManager
from core.search import MessageSearch
from core.reconnect import ReconnectManager, HeartbeatManager
from core.blacklist import Blacklist
from widgets.main_window import MainWindow


# ═══════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ═══════════════════════════════════════════════════════════

APP_NAME = "NOCTURNE"
VERSION = "0.2.0"
ONION_PORT = 9999

STYLE_FILE = Path(__file__).parent / "widgets" / "style.qss"


# ═══════════════════════════════════════════════════════════
# СТИЛЬ
# ═══════════════════════════════════════════════════════════

def load_stylesheet():
    if STYLE_FILE.exists():
        return STYLE_FILE.read_text(encoding="utf-8")
    return ""


# ═══════════════════════════════════════════════════════════
# SPLASH
# ═══════════════════════════════════════════════════════════

def _show_splash(text):
    pix = QPixmap(500, 280)
    pix.fill(QColor("#0a0a0f"))

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    p.setPen(QColor("#8b00ff"))
    p.drawRect(4, 4, 492, 272)
    p.setPen(QColor("#4a0080"))
    p.drawRect(10, 10, 480, 260)

    p.setPen(QColor("#b040ff"))
    font_logo = QFont("Consolas", 32, QFont.Weight.Bold)
    p.setFont(font_logo)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "NOCTURNE")

    p.setPen(QColor("#666"))
    font_sub = QFont("Consolas", 11)
    p.setFont(font_sub)
    p.drawText(0, 200, 500, 30, Qt.AlignmentFlag.AlignCenter,
               "анонимный P2P-мессенджер через Tor")

    p.setPen(QColor("#8b00ff"))
    font_status = QFont("Consolas", 10)
    p.setFont(font_status)
    p.drawText(0, 240, 500, 30, Qt.AlignmentFlag.AlignCenter, text)

    p.end()

    splash = QSplashScreen(pix)
    splash.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    QApplication.processEvents()
    return splash


def _update_splash(splash, text):
    if splash:
        splash.showMessage(
            text,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            QColor("#b040ff"),
        )
        QApplication.processEvents()


def _close_splash(splash):
    if splash:
        splash.close()


# ═══════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ
# ═══════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(load_stylesheet())

    font = QFont("Consolas", 10)
    app.setFont(font)

    # ─── Идентичность ───
    identity = None

    if Identity.exists():
        identity = Identity.load()

    if not identity:
        nickname, ok = QInputDialog.getText(
            None,
            "🦇 NOCTURNE",
            "Добро пожаловать в NOCTURNE!\n\n"
            "Твоя личность будет сгенерирована криптографически.\n"
            "Никаких телефонов, email или имён.\n\n"
            "Введи псевдоним (или оставь пустым):",
        )

        if not ok:
            return

        nickname = (nickname or "").strip() or "anonymous"
        identity = Identity.create(nickname)

        QMessageBox.information(
            None,
            "🦇 NOCTURNE",
            f"Личность создана!\n\n"
            f"UUID:\n{identity.uuid}\n\n"
            f"Отпечаток:\n{identity.fingerprint}\n\n"
            f"Сохрани эти данные — они понадобятся\n"
            f"для связи с тобой.\n\n"
            f"⚠ Приватный ключ хранится только у тебя.\n"
            f"   Никто не сможет его восстановить.",
        )

    # ─── Настройки ───
    settings = Settings()

    # ─── Хранилище ───
    storage_key = hashlib.sha256(identity.private_bytes).digest()
    message_store = MessageStore(encryption_key=storage_key)
    contact_store = ContactStore()

    # ─── Tor Manager ───
    tor = TorManager()

    if not tor.is_available():
        QMessageBox.critical(
            None,
            "🦇 NOCTURNE",
            "Не найден tor.exe!\n\n"
            "Скачай Tor Expert Bundle:\n"
            "https://www.torproject.org/download/tor/\n\n"
            "и распакуй tor.exe в папку tor/ внутри проекта.",
        )
        return

    # ─── Запуск Tor ───
    splash = _show_splash("Запуск Tor...")

    ok, error = tor.start(timeout=90)

    if not ok:
        _close_splash(splash)
        QMessageBox.critical(
            None, "🦇 NOCTURNE",
            f"Не удалось запустить Tor:\n\n{error}",
        )
        return

    _update_splash(splash, "Создание .onion-сервиса...")

    onion, error = tor.create_hidden_service(ONION_PORT)

    if not onion:
        _close_splash(splash)
        QMessageBox.critical(
            None, "🦇 NOCTURNE",
            f"Не удалось создать .onion-сервис:\n\n{error}",
        )
        tor.stop()
        return

    identity.set_onion(onion)

    _update_splash(splash, "Запуск сервера...")

    # ─── Сервер ───
    server = TorServer(port=ONION_PORT)
    ok, error = server.start()

    if not ok:
        _close_splash(splash)
        QMessageBox.critical(
            None, "🦇 NOCTURNE",
            f"Не удалось запустить сервер:\n\n{error}",
        )
        tor.stop()
        return

    _update_splash(splash, "Инициализация модулей...")

    # ─── Очередь ───
    queue = MessageQueue()

    # ─── Транспорт ───
    transport = Transport(identity, queue=queue)
    transport.set_server(server)

    # ─── Менеджеры, зависящие от transport ───
    file_manager = FileManager(lambda u: transport.get_shared_key(u))
    group_manager = GroupManager(identity, lambda u: transport.get_shared_key(u))

    transport.file_manager = file_manager
    transport.group_manager = group_manager

    # ─── UX ───
    notifications = NotificationManager()
    sounds = SoundManager()
    search = MessageSearch(message_store, group_manager)

    _update_splash(splash, "Запуск reconnect...")

    # ─── Reconnect + Heartbeat ───
    reconnect = ReconnectManager(
        transport,
        lambda: contact_store.list_all(),
    )
    reconnect.start()

    heartbeat = HeartbeatManager(transport)
    heartbeat.start()

    # ─── Очередь — процессор ───
    queue_processor = QueueProcessor(queue, transport)
    queue_processor.start()

    _close_splash(splash)

    # ─── GUI ───
    window = MainWindow(
        identity,
        transport,
        message_store,
        settings,
        group_manager=group_manager,
        queue=queue,
        reconnect=reconnect,
        notifications=notifications,
        sounds=sounds,
        search=search,
    )
    window.show()

    # ─── Обработчик выхода ───
    def on_quit():
        try:
            reconnect.stop()
        except Exception:
            pass
        try:
            heartbeat.stop()
        except Exception:
            pass
        try:
            queue_processor.stop()
        except Exception:
            pass
        try:
            transport.shutdown()
        except Exception:
            pass
        try:
            server.stop()
        except Exception:
            pass
        try:
            tor.stop()
        except Exception:
            pass

    app.aboutToQuit.connect(on_quit)

    sys.exit(app.exec())


# ═══════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nВыход.")
        sys.exit(0)
    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)