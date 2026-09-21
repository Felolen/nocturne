from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QTextEdit, QSplitter, QStatusBar,
    QMessageBox, QMenu, QApplication, QInputDialog,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction


class MainWindow(QMainWindow):
    """Главное окно NOCTURNE."""

    contact_selected = pyqtSignal(str)
    message_sent = pyqtSignal(str, str)

    def __init__(self, identity, transport, storage, settings):
        super().__init__()

        self.identity = identity
        self.transport = transport
        self.storage = storage
        self.settings = settings
        self.current_contact = None

        self.setWindowTitle(f"NOCTURNE — {identity.get_display_name()}")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._build_ui()
        self._build_menu()
        self._init_timer()

        if self.transport:
            self.transport.on_message = self._on_incoming_message
            self.transport.on_connect = self._on_contact_connected
            self.transport.on_typing = self._on_typing

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── Верхняя панель ───
        header = QWidget()
        header.setFixedHeight(70)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 12, 24, 12)

        logo = QLabel("🦇 NOCTURNE")
        logo.setObjectName("Title")
        header_layout.addWidget(logo)

        header_layout.addStretch()

        self.status_label = QLabel("● OFFLINE")
        self.status_label.setStyleSheet(
            "color: #666; font-size: 10pt; letter-spacing: 2px; padding: 8px;"
        )
        header_layout.addWidget(self.status_label)

        root.addWidget(header)

        # ─── Splitter ───
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая панель
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 8, 8, 16)
        left_layout.setSpacing(10)

        my_id_label = QLabel(f"МОЙ ID: {self.identity.get_short_id()}")
        my_id_label.setObjectName("Fingerprint")
        my_id_label.setWordWrap(True)
        left_layout.addWidget(my_id_label)

        if self.identity.onion_address:
            onion_label = QLabel(f"🧅 {self.identity.onion_address}")
            onion_label.setObjectName("Fingerprint")
            onion_label.setWordWrap(True)
            left_layout.addWidget(onion_label)

        left_layout.addSpacing(10)

        contacts_title = QLabel("КОНТАКТЫ")
        contacts_title.setObjectName("SectionTitle")
        left_layout.addWidget(contacts_title)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Новый .onion...")
        search_layout.addWidget(self.search_input)

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(40)
        add_btn.clicked.connect(self._add_contact)
        search_layout.addWidget(add_btn)

        left_layout.addLayout(search_layout)

        self.contacts_list = QListWidget()
        self.contacts_list.itemClicked.connect(self._on_contact_clicked)
        self.contacts_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.contacts_list.customContextMenuRequested.connect(
            self._show_contact_menu
        )
        left_layout.addWidget(self.contacts_list, 1)

        splitter.addWidget(left)

        # Правая панель
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 16, 16)
        right_layout.setSpacing(10)

        self.chat_header = QLabel("Выберите контакт")
        self.chat_header.setObjectName("SectionTitle")
        right_layout.addWidget(self.chat_header)

        self.chat_status = QLabel("")
        self.chat_status.setStyleSheet("color: #666; padding: 4px 8px;")
        right_layout.addWidget(self.chat_status)

        self.chat_view = QTextEdit()
        self.chat_view.setObjectName("ChatView")
        self.chat_view.setReadOnly(True)
        right_layout.addWidget(self.chat_view, 1)

        input_layout = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Напиши сообщение...")
        self.message_input.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.message_input, 1)

        send_btn = QPushButton("Отправить 🦇")
        send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(send_btn)

        right_layout.addLayout(input_layout)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([300, 900])

        root.addWidget(splitter, 1)

        # Статус-бар
        status = QStatusBar()
        self.setStatusBar(status)

        self.status_msg = QLabel("Готов")
        status.addWidget(self.status_msg)

        self.tor_status = QLabel("🧅 Tor: ...")
        self.tor_status.setStyleSheet("color: #888;")
        status.addPermanentWidget(self.tor_status)

        self.load_contacts()

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("Файл")

        action_my_id = QAction("Мой ID...", self)
        action_my_id.triggered.connect(self._show_my_id)
        file_menu.addAction(action_my_id)

        action_settings = QAction("Настройки", self)
        action_settings.triggered.connect(self._show_settings)
        file_menu.addAction(action_settings)

        file_menu.addSeparator()

        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        contacts_menu = menubar.addMenu("Контакты")

        action_add = QAction("Добавить по .onion", self)
        action_add.triggered.connect(self._add_contact)
        contacts_menu.addAction(action_add)

        action_refresh = QAction("Обновить список", self)
        action_refresh.triggered.connect(self.load_contacts)
        contacts_menu.addAction(action_refresh)

        help_menu = menubar.addMenu("Помощь")

        action_about = QAction("О программе", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    def _init_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_statuses)
        self.timer.start(2000)

    def _update_statuses(self):
        if not self.transport or not self.transport.server:
            self.status_label.setText("● OFFLINE")
            self.status_label.setStyleSheet(
                "color: #666; font-size: 10pt; padding: 8px;"
            )
            return

        if self.transport.server.running:
            count = self.transport.server.get_client_count()
            self.status_label.setText(f"● ONLINE ({count})")
            self.status_label.setStyleSheet(
                "color: #44cc44; font-size: 10pt; "
                "letter-spacing: 2px; padding: 8px;"
            )
        else:
            self.status_label.setText("● OFFLINE")
            self.status_label.setStyleSheet(
                "color: #666; font-size: 10pt; padding: 8px;"
            )

        if self.identity.onion_address:
            onion = self.identity.onion_address
            self.tor_status.setText(f"🧅 {onion[:20]}...")
        else:
            self.tor_status.setText("🧅 Tor: не подключён")

    def load_contacts(self):
        self.contacts_list.clear()

        from core.storage import ContactStore
        store = ContactStore()
        contacts = store.list_all()

        for c in contacts:
            uuid = c["uuid"]
            nickname = c.get("nickname", "unknown")
            fp = c.get("fingerprint", "")

            online = False
            if self.transport:
                online = self.transport.is_contact_online(uuid)

            status_icon = "🟢" if online else "⚫"

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, uuid)
            item.setText(f"{status_icon}  {nickname}")

            fp_text = fp[:16] if fp else uuid[:16]
            item.setToolTip(f"{nickname}\n{fp_text}")

            self.contacts_list.addItem(item)

    def _on_contact_clicked(self, item):
        uuid = item.data(Qt.ItemDataRole.UserRole)
        if uuid:
            self.open_chat(uuid)

    def _show_contact_menu(self, position):
        item = self.contacts_list.itemAt(position)
        if not item:
            return

        uuid = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)

        action_open = QAction("Открыть чат", self)
        action_open.triggered.connect(lambda: self.open_chat(uuid))
        menu.addAction(action_open)

        action_copy = QAction("Копировать ID", self)
        action_copy.triggered.connect(lambda: self._copy_to_clipboard(uuid))
        menu.addAction(action_copy)

        menu.addSeparator()

        action_delete = QAction("Удалить контакт", self)
        action_delete.triggered.connect(lambda: self._delete_contact(uuid))
        menu.addAction(action_delete)

        menu.exec(self.contacts_list.mapToGlobal(position))

    def _copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        self.status_msg.setText(f"Скопировано: {text[:30]}...")

    def _delete_contact(self, uuid):
        reply = QMessageBox.question(
            self, "Удалить контакт",
            f"Удалить контакт?\n\n{uuid}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.storage import ContactStore
            store = ContactStore()
            store.remove(uuid)
            self.load_contacts()
            self.status_msg.setText("Контакт удалён")

    def open_chat(self, uuid):
        from core.storage import ContactStore
        store = ContactStore()
        contact_data = store.get(uuid)

        if not contact_data:
            return

        self.current_contact = uuid
        nickname = contact_data.get("nickname", "unknown")

        self.chat_header.setText(f"💬 {nickname}")

        online = False
        if self.transport:
            online = self.transport.is_contact_online(uuid)

        if online:
            self.chat_status.setText("🟢 online")
            self.chat_status.setStyleSheet("color: #44cc44; padding: 4px 8px;")
        else:
            self.chat_status.setText("⚫ offline")
            self.chat_status.setStyleSheet("color: #666; padding: 4px 8px;")

        self._load_messages(uuid)
        self.message_input.setFocus()

    def _load_messages(self, uuid):
        self.chat_view.clear()

        messages = self.storage.get_messages(uuid, limit=200)

        if not messages:
            self.chat_view.setHtml(
                "<div style='color:#444; text-align:center; padding:40px;'>"
                "🦇 Начало переписки<br><br>"
                "<span style='font-size:9pt;'>"
                "Сообщения защищены E2E-шифрованием"
                "</span></div>"
            )
            return

        html_parts = []

        for m in messages:
            direction = m["direction"]
            text = m["text"].replace("<", "&lt;").replace(">", "&gt;")
            ts = m["timestamp"][:19].replace("T", " ")

            if direction == "out":
                html_parts.append(f"""
                <div style="text-align: right; margin: 8px 0;">
                    <span style="color: #444; font-size: 8pt;">{ts} · Вы</span><br>
                    <span style="background: #1a0030; color: #cc44ff;
                                 padding: 8px 14px; border-radius: 10px;
                                 display: inline-block; max-width: 70%;
                                 text-align: left;">{text}</span>
                </div>
                """)
            else:
                html_parts.append(f"""
                <div style="text-align: left; margin: 8px 0;">
                    <span style="color: #444; font-size: 8pt;">Собеседник · {ts}</span><br>
                    <span style="background: #002a15; color: #66ff99;
                                 padding: 8px 14px; border-radius: 10px;
                                 display: inline-block; max-width: 70%;">{text}</span>
                </div>
                """)

        self.chat_view.setHtml("".join(html_parts))
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        scrollbar = self.chat_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _send_message(self):
        if not self.current_contact:
            QMessageBox.warning(self, "NOCTURNE", "Выбери контакт")
            return

        text = self.message_input.text().strip()
        if not text:
            return

        if self.transport:
            success, error = self.transport.send_message(
                self.current_contact, text
            )

            if not success:
                QMessageBox.warning(
                    self, "NOCTURNE",
                    f"Не удалось отправить:\n{error}"
                )
                return

        import time
        msg_id = f"msg-{time.time()}"
        self.storage.add_message(msg_id, self.current_contact, "out", text)

        self.message_input.clear()
        self._load_messages(self.current_contact)

        self.status_msg.setText("Отправлено ✓")

    def _on_incoming_message(self, uuid, text, msg_id, ts):
        self.storage.add_message(msg_id, uuid, "in", text, ts)

        if self.current_contact == uuid:
            self._load_messages(uuid)

        self.status_msg.setText(f"Новое сообщение от {uuid[:8]}...")

    def _on_contact_connected(self, client_id, contact):
        if contact:
            from core.storage import ContactStore
            store = ContactStore()
            store.add(contact)
            self.load_contacts()

        self.status_msg.setText("Контакт подключился")

    def _on_typing(self, client_id, is_typing):
        if is_typing and self.current_contact:
            self.chat_status.setText("✎ печатает...")
        else:
            online = False
            if self.transport and self.current_contact:
                online = self.transport.is_contact_online(self.current_contact)
            self.chat_status.setText("🟢 online" if online else "⚫ offline")

    def _add_contact(self):
        onion, ok = QInputDialog.getText(
            self, "Добавить контакт",
            "Введи .onion-адрес контакта:"
        )

        if not ok or not onion:
            return

        onion = onion.strip()

        if not onion.endswith(".onion"):
            onion += ".onion"

        self.status_msg.setText(f"Подключаюсь к {onion[:30]}...")

        if self.transport:
            success, error = self.transport.connect_to(onion)

            if not success:
                QMessageBox.warning(
                    self, "NOCTURNE",
                    f"Не удалось подключиться:\n{error}"
                )
                return

            self.status_msg.setText("Подключение установлено")

    def _show_my_id(self):
        text = (
            f"═══ МОЙ NOCTURNE ID ═══\n\n"
            f"UUID:\n{self.identity.uuid}\n\n"
            f"Отпечаток:\n{self.identity.fingerprint}\n\n"
            f"Короткий ID:\n{self.identity.get_short_id()}\n\n"
        )

        if self.identity.onion_address:
            text += f"🧅 .onion-адрес:\n{self.identity.onion_address}\n\n"
        else:
            text += "🧅 Tor ещё не запущен\n\n"

        text += (
            "Передай .onion-адрес собеседнику,\n"
            "чтобы он смог подключиться."
        )

        QMessageBox.information(self, "Мой ID", text)

    def _show_settings(self):
        QMessageBox.information(
            self, "Настройки",
            "Настройки в разработке 🦇\n\n"
            "Скоро:\n"
            "• Смена темы\n"
            "• Уведомления\n"
            "• Автоочистка истории"
        )

    def _show_about(self):
        QMessageBox.about(
            self, "О NOCTURNE",
            "<h2 style='color:#b040ff;'>🦇 NOCTURNE</h2>"
            "<p>Анонимный P2P-мессенджер через Tor</p>"
            "<p style='color:#888;'>"
            "• X25519 + AES-256-GCM<br>"
            "• Никаких серверов<br>"
            "• Скрытые .onion-сервисы<br>"
            "• E2E-шифрование<br>"
            "• Никаких телефонов и email"
            "</p>"
            "<p style='color:#444; font-size:9pt;'>"
            "github.com/Felolen/nocturne</p>"
        )

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Выход",
            "Выйти из NOCTURNE?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.transport:
                self.transport.shutdown()
            event.accept()
        else:
            event.ignore()