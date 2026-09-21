import time
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QTextEdit, QSplitter, QStatusBar,
    QMessageBox, QMenu, QApplication, QInputDialog,
    QFileDialog, QDialog, QDialogButtonBox, QCheckBox,
    QScrollArea, QFrame, QTabWidget, QComboBox, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont


class MainWindow(QMainWindow):
    """Главное окно NOCTURNE v0.2."""

    def __init__(self, identity, transport, storage, settings,
                 group_manager=None, queue=None, reconnect=None,
                 notifications=None, sounds=None, search=None):
        super().__init__()

        self.identity = identity
        self.transport = transport
        self.storage = storage
        self.settings = settings
        self.group_manager = group_manager
        self.queue = queue
        self.reconnect = reconnect
        self.notifications = notifications
        self.sounds = sounds
        self.search = search

        self.current_contact = None
        self.current_group = None
        self.mode = "contacts"  # contacts / groups

        self.setWindowTitle(f"NOCTURNE — {identity.get_display_name()}")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)
        self.setAcceptDrops(True)

        self._build_ui()
        self._build_menu()
        self._init_timer()
        self._connect_signals()

    # ═══════════════════════════════════════════════════════
    # UI
    # ═══════════════════════════════════════════════════════

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
            "color: #666; font-size: 10pt; "
            "letter-spacing: 2px; padding: 8px;"
        )
        header_layout.addWidget(self.status_label)

        root.addWidget(header)

        # ─── Splitter ───
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ─── Левая панель ───
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 8, 8, 16)
        left_layout.setSpacing(10)

        # мой ID
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

        # переключатель режимов
        mode_layout = QHBoxLayout()

        self.btn_contacts = QPushButton("👤 Контакты")
        self.btn_contacts.setCheckable(True)
        self.btn_contacts.setChecked(True)
        self.btn_contacts.clicked.connect(lambda: self._set_mode("contacts"))
        mode_layout.addWidget(self.btn_contacts)

        self.btn_groups = QPushButton("👥 Группы")
        self.btn_groups.setCheckable(True)
        self.btn_groups.clicked.connect(lambda: self._set_mode("groups"))
        mode_layout.addWidget(self.btn_groups)

        left_layout.addLayout(mode_layout)

        # поиск
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск...")
        self.search_input.textChanged.connect(self._on_search)
        left_layout.addWidget(self.search_input)

        # кнопки добавления
        add_layout = QHBoxLayout()

        self.add_btn = QPushButton("+ .onion")
        self.add_btn.clicked.connect(self._add_contact)
        add_layout.addWidget(self.add_btn)

        self.new_group_btn = QPushButton("+ Группа")
        self.new_group_btn.clicked.connect(self._create_group)
        self.new_group_btn.setVisible(False)
        add_layout.addWidget(self.new_group_btn)

        left_layout.addLayout(add_layout)

        # список
        self.contacts_list = QListWidget()
        self.contacts_list.itemClicked.connect(self._on_list_clicked)
        self.contacts_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.contacts_list.customContextMenuRequested.connect(
            self._show_context_menu
        )
        left_layout.addWidget(self.contacts_list, 1)

        splitter.addWidget(left)

        # ─── Правая панель ───
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 16, 16)
        right_layout.setSpacing(10)

        # заголовок чата
        chat_header_layout = QHBoxLayout()

        self.chat_header = QLabel("Выберите контакт")
        self.chat_header.setObjectName("SectionTitle")
        chat_header_layout.addWidget(self.chat_header)

        chat_header_layout.addStretch()

        self.verify_btn = QPushButton("🔐")
        self.verify_btn.setToolTip("Проверить fingerprint")
        self.verify_btn.setFixedWidth(40)
        self.verify_btn.clicked.connect(self._verify_fingerprint)
        self.verify_btn.setVisible(False)
        chat_header_layout.addWidget(self.verify_btn)

        self.block_btn = QPushButton("🚫")
        self.block_btn.setToolTip("Заблокировать")
        self.block_btn.setFixedWidth(40)
        self.block_btn.clicked.connect(self._block_contact)
        self.block_btn.setVisible(False)
        chat_header_layout.addWidget(self.block_btn)

        right_layout.addLayout(chat_header_layout)

        self.chat_status = QLabel("")
        self.chat_status.setStyleSheet("color: #666; padding: 4px 8px;")
        right_layout.addWidget(self.chat_status)

        # область сообщений
        self.chat_view = QTextEdit()
        self.chat_view.setObjectName("ChatView")
        self.chat_view.setReadOnly(True)
        right_layout.addWidget(self.chat_view, 1)

        # панель ввода
        input_layout = QHBoxLayout()

        self.attach_btn = QPushButton("📎")
        self.attach_btn.setFixedWidth(40)
        self.attach_btn.clicked.connect(self._attach_file)
        input_layout.addWidget(self.attach_btn)

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Напиши сообщение...")
        self.message_input.returnPressed.connect(self._send_message)
        self.message_input.textChanged.connect(self._on_input_changed)
        input_layout.addWidget(self.message_input, 1)

        self.send_btn = QPushButton("Отправить 🦇")
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        right_layout.addLayout(input_layout)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([320, 1000])

        root.addWidget(splitter, 1)

        # ─── Статус-бар ───
        status = QStatusBar()
        self.setStatusBar(status)

        self.status_msg = QLabel("Готов")
        status.addWidget(self.status_msg)

        self.queue_label = QLabel("")
        self.queue_label.setStyleSheet("color: #888;")
        status.addPermanentWidget(self.queue_label)

        self.tor_status = QLabel("🧅 Tor: ...")
        self.tor_status.setStyleSheet("color: #888;")
        status.addPermanentWidget(self.tor_status)

        self.load_contacts()

    def _build_menu(self):
        menubar = self.menuBar()

        # Файл
        file_menu = menubar.addMenu("Файл")

        action_my_id = QAction("Мой ID...", self)
        action_my_id.triggered.connect(self._show_my_id)
        file_menu.addAction(action_my_id)

        action_export = QAction("Экспорт чата...", self)
        action_export.triggered.connect(self._export_chat)
        file_menu.addAction(action_export)

        action_backup = QAction("Backup...", self)
        action_backup.triggered.connect(self._create_backup)
        file_menu.addAction(action_backup)

        file_menu.addSeparator()

        action_settings = QAction("Настройки", self)
        action_settings.triggered.connect(self._show_settings)
        file_menu.addAction(action_settings)

        file_menu.addSeparator()

        action_quit = QAction("Выход", self)
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        # Контакты
        contacts_menu = menubar.addMenu("Контакты")

        action_add = QAction("Добавить по .onion", self)
        action_add.triggered.connect(self._add_contact)
        contacts_menu.addAction(action_add)

        action_search = QAction("Поиск в сообщениях...", self)
        action_search.triggered.connect(self._search_messages)
        contacts_menu.addAction(action_search)

        action_refresh = QAction("Обновить", self)
        action_refresh.triggered.connect(self.load_contacts)
        contacts_menu.addAction(action_refresh)

        # Помощь
        help_menu = menubar.addMenu("Помощь")

        action_about = QAction("О программе", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

    def _init_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_statuses)
        self.timer.start(2000)

    def _connect_signals(self):
        if self.transport:
            self.transport.on_message = self._on_incoming_message
            self.transport.on_connect = self._on_contact_connected
            self.transport.on_typing = self._on_remote_typing
            self.transport.on_file_complete = self._on_file_complete
            self.transport.on_file_progress = self._on_file_progress
            self.transport.on_group_message = self._on_group_message
            self.transport.on_group_invite = self._on_group_invite
            self.transport.on_read = self._on_read_receipt

    def _update_statuses(self):
        if self.transport and self.transport.server:
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

        if self.queue:
            size = self.queue.size()
            if size > 0:
                self.queue_label.setText(f"📤 В очереди: {size}")
            else:
                self.queue_label.setText("")

    # ═══════════════════════════════════════════════════════
    # СПИСКИ / КОНТАКТЫ
    # ═══════════════════════════════════════════════════════

    def _set_mode(self, mode):
        self.mode = mode
        self.btn_contacts.setChecked(mode == "contacts")
        self.btn_groups.setChecked(mode == "groups")
        self.new_group_btn.setVisible(mode == "groups")
        self.add_btn.setVisible(mode == "contacts")
        self.load_contacts()

    def load_contacts(self):
        self.contacts_list.clear()

        if self.mode == "contacts":
            self._load_contacts_list()
        else:
            self._load_groups_list()

    def _load_contacts_list(self):
        from core.storage import ContactStore
        store = ContactStore()
        contacts = store.list_all()

        query = self.search_input.text().strip().lower()

        for c in contacts:
            uuid = c["uuid"]
            nickname = c.get("nickname", "unknown")
            fp = c.get("fingerprint", "")

            if query:
                haystack = f"{nickname} {fp} {uuid}".lower()
                if query not in haystack:
                    continue

            online = False
            if self.transport:
                online = self.transport.is_contact_online(uuid)

            unread = self.storage.get_unread_count(uuid)

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, ("contact", uuid))

            status_icon = "🟢" if online else "⚫"

            text = f"{status_icon}  {nickname}"
            if unread > 0:
                text += f"  ({unread})"

            item.setText(text)
            item.setToolTip(f"{nickname}\n{fp}")

            if unread > 0:
                item.setForeground(Qt.GlobalColor.white)

            self.contacts_list.addItem(item)

    def _load_groups_list(self):
        if not self.group_manager:
            return

        query = self.search_input.text().strip().lower()

        for group in self.group_manager.list_groups():
            if query:
                if query not in group.name.lower():
                    continue

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, ("group", group.group_id))

            text = f"👥  {group.name}  ({group.member_count()})"
            item.setText(text)
            item.setToolTip(f"{group.name}\nУчастников: {group.member_count()}")

            self.contacts_list.addItem(item)

    def _on_search(self, text):
        self.load_contacts()

    def _on_list_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        mode, identifier = data

        if mode == "contact":
            self.open_chat(identifier)
        elif mode == "group":
            self.open_group(identifier)

    # ═══════════════════════════════════════════════════════
    # ЧАТЫ
    # ═══════════════════════════════════════════════════════

    def open_chat(self, uuid):
        from core.storage import ContactStore
        store = ContactStore()
        contact_data = store.get(uuid)

        if not contact_data:
            return

        self.current_contact = uuid
        self.current_group = None

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

        self.verify_btn.setVisible(True)
        self.block_btn.setVisible(True)

        self._load_messages(uuid)
        self.message_input.setFocus()

        self.storage.mark_all_read(uuid)
        self.load_contacts()

    def open_group(self, group_id):
        if not self.group_manager:
            return

        group = self.group_manager.get_group(group_id)
        if not group:
            return

        self.current_group = group_id
        self.current_contact = None

        self.chat_header.setText(f"👥 {group.name}")

        names = []
        for uuid, data in group.members.items():
            nickname = data.get("nickname", "unknown")
            role = data.get("role", "member")
            if role == "admin":
                names.append(f"👑 {nickname}")
            else:
                names.append(nickname)

        self.chat_status.setText(
            f"{group.member_count()} участников: " + ", ".join(names[:5])
        )
        self.chat_status.setStyleSheet("color: #888; padding: 4px 8px;")

        self.verify_btn.setVisible(False)
        self.block_btn.setVisible(False)

        self._load_group_messages(group)

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

        html_parts = self._render_messages(messages, uuid)
        self.chat_view.setHtml("".join(html_parts))
        self._scroll_to_bottom()

    def _load_group_messages(self, group):
        self.chat_view.clear()

        messages = group.messages[-200:]

        if not messages:
            self.chat_view.setHtml(
                "<div style='color:#444; text-align:center; padding:40px;'>"
                "🦇 Начало группового чата<br><br>"
                "<span style='font-size:9pt;'>"
                "Групповое E2E-шифрование"
                "</span></div>"
            )
            return

        html_parts = []

        for m in messages:
            sender_uuid = m.get("sender_uuid", "")
            text = m.get("text", "").replace("<", "&lt;").replace(">", "&gt;")
            ts = m.get("timestamp", "")[:19].replace("T", " ")

            member = group.members.get(sender_uuid, {})
            sender_name = member.get("nickname", sender_uuid[:8])

            is_mine = sender_uuid == self.identity.uuid

            if is_mine:
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
                    <span style="color: #8b00ff; font-size: 8pt; font-weight: bold;">
                        {sender_name}
                    </span>
                    <span style="color: #444; font-size: 8pt;"> · {ts}</span><br>
                    <span style="background: #002a15; color: #66ff99;
                                 padding: 8px 14px; border-radius: 10px;
                                 display: inline-block; max-width: 70%;">{text}</span>
                </div>
                """)

        self.chat_view.setHtml("".join(html_parts))
        self._scroll_to_bottom()

    def _render_messages(self, messages, contact_uuid):
        html_parts = []

        for m in messages:
            direction = m["direction"]
            text = m["text"].replace("<", "&lt;").replace(">", "&gt;")
            ts = m["timestamp"][:19].replace("T", " ")

            if m.get("is_file"):
                file_name = m.get("file_name", "file")
                file_size = m.get("file_size", 0)

                size_str = self._human_size(file_size)

                file_html = (
                    f"📎 <b>{file_name}</b><br>"
                    f"<span style='font-size:9pt; color:#888;'>{size_str}</span>"
                )

                if direction == "out":
                    html_parts.append(f"""
                    <div style="text-align: right; margin: 8px 0;">
                        <span style="color: #444; font-size: 8pt;">{ts} · Вы</span><br>
                        <span style="background: #1a0030; color: #cc44ff;
                                     padding: 8px 14px; border-radius: 10px;
                                     display: inline-block;">{file_html}</span>
                    </div>
                    """)
                else:
                    html_parts.append(f"""
                    <div style="text-align: left; margin: 8px 0;">
                        <span style="color: #444; font-size: 8pt;">Собеседник · {ts}</span><br>
                        <span style="background: #002a15; color: #66ff99;
                                     padding: 8px 14px; border-radius: 10px;
                                     display: inline-block;">{file_html}</span>
                    </div>
                    """)
                continue

            edited_mark = " <span style='font-size:7pt; color:#666;'>(изменено)</span>" if m.get("edited") else ""
            read_mark = ""
            if direction == "out" and m.get("read"):
                read_mark = " <span style='color:#44cc44; font-size:8pt;'>✓✓</span>"
            elif direction == "out":
                read_mark = " <span style='color:#666; font-size:8pt;'>✓</span>"

            if direction == "out":
                html_parts.append(f"""
                <div style="text-align: right; margin: 8px 0;">
                    <span style="color: #444; font-size: 8pt;">{ts} · Вы{edited_mark}</span>
                    <span>{read_mark}</span><br>
                    <span style="background: #1a0030; color: #cc44ff;
                                 padding: 8px 14px; border-radius: 10px;
                                 display: inline-block; max-width: 70%;
                                 text-align: left;">{text}</span>
                </div>
                """)
            else:
                html_parts.append(f"""
                <div style="text-align: left; margin: 8px 0;">
                    <span style="color: #444; font-size: 8pt;">Собеседник · {ts}{edited_mark}</span><br>
                    <span style="background: #002a15; color: #66ff99;
                                 padding: 8px 14px; border-radius: 10px;
                                 display: inline-block; max-width: 70%;">{text}</span>
                </div>
                """)

        return html_parts

    @staticmethod
    def _human_size(n):
        for unit in ("B", "KB", "MB", "GB"):
            if abs(n) < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    def _scroll_to_bottom(self):
        scrollbar = self.chat_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ═══════════════════════════════════════════════════════
    # ВВОД
    # ═══════════════════════════════════════════════════════

    def _on_input_changed(self, text):
        """Вызывается при вводе текста."""
        if not self.current_contact or not self.transport:
            return

        if len(text) > 0:
            self.transport.broadcast_typing(self.current_contact, True)
        else:
            self.transport.broadcast_typing(self.current_contact, False)

    def _on_remote_typing(self, uuid, is_typing):
        """Вызывается транспортом при получении TYPING."""
        if not self.current_contact:
            return

        if is_typing:
            self.chat_status.setText("✎ печатает...")
        else:
            online = False
            if self.transport:
                online = self.transport.is_contact_online(self.current_contact)
            self.chat_status.setText("🟢 online" if online else "⚫ offline")

    def _send_message(self):
        text = self.message_input.text().strip()
        if not text:
            return

        if self.current_group:
            self._send_group_message(text)
        elif self.current_contact:
            self._send_contact_message(text)
        else:
            QMessageBox.warning(self, "NOCTURNE", "Выбери контакт или группу")
            return

        self.message_input.clear()

    def _send_contact_message(self, text):
        success, error = self.transport.send_message(self.current_contact, text)

        if not success:
            QMessageBox.warning(self, "NOCTURNE", f"Ошибка:\n{error}")
            return

        msg_id = f"msg-{time.time()}"
        self.storage.add_message(msg_id, self.current_contact, "out", text)

        self._load_messages(self.current_contact)

        if self.sounds:
            self.sounds.play_message()

        if error == "queued":
            self.status_msg.setText("📤 Сообщение в очереди")

    def _send_group_message(self, text):
        success, error = self.transport.send_group_message(
            self.current_group, text
        )

        if not success:
            QMessageBox.warning(self, "NOCTURNE", f"Ошибка:\n{error}")
            return

        group = self.group_manager.get_group(self.current_group)
        if group:
            self._load_group_messages(group)

    def _attach_file(self):
        if not self.current_contact:
            QMessageBox.warning(self, "NOCTURNE", "Выбери контакт")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери файл", "",
            "Все файлы (*.*)"
        )

        if not path:
            return

        self._send_file(path)

    def _send_file(self, file_path):
        path = Path(file_path)

        if not path.exists():
            QMessageBox.warning(self, "NOCTURNE", "Файл не найден")
            return

        size = path.stat().st_size
        if size > 50 * 1024 * 1024:
            QMessageBox.warning(
                self, "NOCTURNE",
                "Файл слишком большой (макс. 50 MB)"
            )
            return

        self.status_msg.setText(f"📤 Отправка {path.name}...")

        success, result = self.transport.send_file(
            self.current_contact, str(path)
        )

        if success:
            msg_id = f"file-{time.time()}"
            self.storage.add_message(
                msg_id, self.current_contact, "out",
                f"[Файл: {path.name}]",
                is_file=True,
                file_name=path.name,
                file_size=size,
            )

            self._load_messages(self.current_contact)
            self.status_msg.setText(f"✓ Отправлено: {path.name}")

            if self.sounds:
                self.sounds.play_file()
        else:
            QMessageBox.warning(self, "NOCTURNE", f"Ошибка: {result}")

    # ═══════════════════════════════════════════════════════
    # CALLBACKS ИЗ ТРАНСПОРТА
    # ═══════════════════════════════════════════════════════

    def _on_incoming_message(self, uuid, text, msg_id, ts, reply_to=None):
        self.storage.add_message(msg_id, uuid, "in", text, ts, reply_to)

        if self.current_contact == uuid:
            self._load_messages(uuid)
            self.storage.mark_read(msg_id)
            if self.transport:
                self.transport.send_read(uuid, msg_id)
        else:
            if self.notifications and self.settings.get("notifications"):
                from core.storage import ContactStore
                store = ContactStore()
                contact = store.get(uuid)
                nickname = contact.get("nickname", uuid[:8]) if contact else uuid[:8]

                self.notifications.notify_message(nickname, text)

            if self.sounds and self.settings.get("sounds"):
                self.sounds.play_message()

            self.load_contacts()

    def _on_group_message(self, uuid, payload):
        group_id = payload.get("group_id")
        encrypted = payload.get("data")
        msg_id = payload.get("id")
        ts = payload.get("time")

        if not self.group_manager:
            return

        message_data, error = self.group_manager.receive_message(
            group_id, encrypted, uuid, msg_id, ts
        )

        if message_data and self.current_group == group_id:
            group = self.group_manager.get_group(group_id)
            if group:
                self._load_group_messages(group)

        if self.sounds and self.settings.get("sounds"):
            self.sounds.play_message()

    def _on_group_invite(self, uuid, payload):
        group_id = payload.get("group_id")
        name = payload.get("name")
        inviter = payload.get("inviter_nickname", "unknown")

        reply = QMessageBox.question(
            self, "Приглашение в группу",
            f"{inviter} приглашает тебя в группу «{name}»\n\nПринять?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.group_ui import GroupUIHelper

            helper = GroupUIHelper(self.group_manager, self.transport, self.identity)
            group = helper.handle_incoming_invite(payload, uuid)

            if group:
                helper.accept_invite(group_id)
                self._set_mode("groups")
                self.status_msg.setText(f"Присоединился к «{name}»")

    def _on_contact_connected(self, client_id, contact):
        if contact:
            from core.storage import ContactStore
            store = ContactStore()
            store.add(contact)
            self.load_contacts()

            if self.sounds and self.settings.get("sounds"):
                self.sounds.play_connect()

    def _on_read_receipt(self, uuid, msg_id):
        if self.current_contact == uuid:
            self._load_messages(uuid)

    def _on_file_progress(self, uuid, file_id, percent):
        self.status_msg.setText(f"📥 Получение файла... {percent:.0f}%")

    def _on_file_complete(self, uuid, file_id, path):
        self.status_msg.setText(f"✓ Файл получен: {Path(path).name}")

        self.storage.add_message(
            f"recv-{file_id}", uuid, "in",
            f"[Файл получен: {Path(path).name}]",
            is_file=True,
            file_name=Path(path).name,
            file_size=Path(path).stat().st_size if Path(path).exists() else 0,
        )

        if self.current_contact == uuid:
            self._load_messages(uuid)

        if self.notifications and self.settings.get("notifications"):
            from core.storage import ContactStore
            store = ContactStore()
            contact = store.get(uuid)
            nickname = contact.get("nickname", uuid[:8]) if contact else uuid[:8]

            self.notifications.notify_file(
                nickname, Path(path).name,
                Path(path).stat().st_size if Path(path).exists() else 0,
            )

        if self.sounds and self.settings.get("sounds"):
            self.sounds.play_file()

    # ═══════════════════════════════════════════════════════
    # ДЕЙСТВИЯ
    # ═══════════════════════════════════════════════════════

    def _add_contact(self):
        onion, ok = QInputDialog.getText(
            self, "Добавить контакт",
            "Введи .onion-адрес:"
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

    def _create_group(self):
        if not self.group_manager:
            QMessageBox.warning(
                self, "NOCTURNE",
                "Группы недоступны — group_manager не инициализирован."
            )
            return

        from widgets.groups_widget import CreateGroupDialog

        dlg = CreateGroupDialog(self)
        if dlg.exec():
            data = dlg.get_data()

            if not data["name"]:
                QMessageBox.warning(self, "NOCTURNE", "Введи имя группы")
                return

            from core.group_ui import GroupUIHelper

            helper = GroupUIHelper(self.group_manager, self.transport, self.identity)

            group = helper.create_and_broadcast(
                data["name"], data["members"]
            )

            if group:
                self._set_mode("groups")
                self.load_contacts()
                self.status_msg.setText(f"✓ Группа «{group.name}» создана")

    def _show_context_menu(self, position):
        item = self.contacts_list.itemAt(position)
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        mode, identifier = data

        menu = QMenu(self)

        if mode == "contact":
            action_open = QAction("Открыть чат", self)
            action_open.triggered.connect(lambda: self.open_chat(identifier))
            menu.addAction(action_open)

            action_verify = QAction("🔐 Проверить fingerprint", self)
            action_verify.triggered.connect(self._verify_fingerprint)
            menu.addAction(action_verify)

            action_copy = QAction("Копировать ID", self)
            action_copy.triggered.connect(
                lambda: self._copy_to_clipboard(identifier)
            )
            menu.addAction(action_copy)

            menu.addSeparator()

            action_clear = QAction("Очистить историю", self)
            action_clear.triggered.connect(
                lambda: self._clear_history(identifier)
            )
            menu.addAction(action_clear)

            action_block = QAction("🚫 Заблокировать", self)
            action_block.triggered.connect(
                lambda: self._block_contact(identifier)
            )
            menu.addAction(action_block)

            menu.addSeparator()

            action_delete = QAction("Удалить контакт", self)
            action_delete.triggered.connect(
                lambda: self._delete_contact(identifier)
            )
            menu.addAction(action_delete)

        elif mode == "group":
            action_open = QAction("Открыть группу", self)
            action_open.triggered.connect(lambda: self.open_group(identifier))
            menu.addAction(action_open)

            menu.addSeparator()

            action_leave = QAction("Выйти из группы", self)
            action_leave.triggered.connect(
                lambda: self._leave_group(identifier)
            )
            menu.addAction(action_leave)

        menu.exec(self.contacts_list.mapToGlobal(position))

    def _copy_to_clipboard(self, text):
        QApplication.clipboard().setText(text)
        self.status_msg.setText(f"Скопировано: {text[:30]}...")

    def _clear_history(self, uuid):
        reply = QMessageBox.question(
            self, "Очистить историю",
            "Удалить все сообщения с этим контактом?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.storage.delete_conversation(uuid)
            if self.current_contact == uuid:
                self._load_messages(uuid)
            self.status_msg.setText("История очищена")

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

    def _leave_group(self, group_id):
        reply = QMessageBox.question(
            self, "Выйти из группы",
            "Покинуть эту группу?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.group_ui import GroupUIHelper

            helper = GroupUIHelper(self.group_manager, self.transport, self.identity)
            helper.leave_group(group_id)

            self.load_contacts()
            self.status_msg.setText("Покинул группу")

    def _verify_fingerprint(self):
        if not self.current_contact:
            return

        from core.storage import ContactStore
        store = ContactStore()
        contact = store.get(self.current_contact)

        if not contact:
            return

        fp = contact.get("fingerprint", "")
        nickname = contact.get("nickname", "unknown")

        text = (
            f"═══ FINGERPRINT КОНТАКТА ═══\n\n"
            f"Имя: {nickname}\n\n"
            f"Отпечаток:\n{fp}\n\n"
            f"Сравни с отпечатком у собеседника.\n"
            f"Если совпадает — соединение безопасно.\n\n"
            f"⚠ Если НЕ совпадает — возможен MITM!"
        )

        QMessageBox.information(self, "Проверка fingerprint", text)

    def _block_contact(self, uuid=None):
        uuid = uuid or self.current_contact
        if not uuid:
            return

        reply = QMessageBox.question(
            self, "Блокировка",
            f"Заблокировать контакт?\n\n{uuid}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.blacklist import Blacklist

            bl = Blacklist()
            bl.block(uuid, "заблокирован пользователем")

            self.status_msg.setText("Контакт заблокирован")
            self.load_contacts()

    def _search_messages(self):
        if not self.search:
            return

        query, ok = QInputDialog.getText(
            self, "Поиск в сообщениях",
            "Введи текст для поиска:"
        )

        if not ok or not query:
            return

        results = self.search.search_everywhere(query)

        total = results["total"]

        if total == 0:
            QMessageBox.information(
                self, "Поиск",
                f"Ничего не найдено по запросу: {query}"
            )
            return

        text = f"═══ РЕЗУЛЬТАТЫ ПОИСКА ═══\n\n"
        text += f"Запрос: {query}\n"
        text += f"Найдено: {total}\n\n"

        if results["personal"]:
            text += f"📋 Личные чаты: {len(results['personal'])}\n"

        if results["groups"]:
            text += f"👥 Группы: {len(results['groups'])}\n"

        QMessageBox.information(self, "Результаты поиска", text)

    def _export_chat(self):
        if not self.current_contact and not self.current_group:
            QMessageBox.warning(self, "NOCTURNE", "Выбери чат")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт чата",
            "chat_export.txt",
            "Text files (*.txt);;JSON (*.json)"
        )

        if not path:
            return

        try:
            if self.current_contact:
                self._export_contact_chat(path)
            elif self.current_group:
                self._export_group_chat(path)

            self.status_msg.setText(f"✓ Экспортировано: {path}")
        except Exception as e:
            QMessageBox.warning(self, "NOCTURNE", f"Ошибка: {e}")

    def _export_contact_chat(self, path):
        messages = self.storage.get_messages(self.current_contact, limit=10000)

        if path.endswith(".json"):
            import json
            data = {
                "contact_uuid": self.current_contact,
                "exported": datetime.now().isoformat(),
                "messages": messages,
            }
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            lines = [f"=== Экспорт чата {self.current_contact} ===\n"]
            for m in messages:
                direction = "Вы" if m["direction"] == "out" else "Собеседник"
                lines.append(f"[{m['timestamp']}] {direction}: {m['text']}\n")
            Path(path).write_text("\n".join(lines), encoding="utf-8")

    def _export_group_chat(self, path):
        group = self.group_manager.get_group(self.current_group)
        if not group:
            return

        messages = group.messages

        if path.endswith(".json"):
            import json
            data = {
                "group_id": group.group_id,
                "group_name": group.name,
                "exported": datetime.now().isoformat(),
                "messages": messages,
            }
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            lines = [f"=== Экспорт группы {group.name} ===\n"]
            for m in messages:
                sender = group.members.get(m.get("sender_uuid"), {})
                nickname = sender.get("nickname", "unknown")
                lines.append(
                    f"[{m.get('timestamp')}] {nickname}: {m.get('text')}\n"
                )
            Path(path).write_text("\n".join(lines), encoding="utf-8")

    def _create_backup(self):
        try:
            from core.backup import create_backup
        except ImportError:
            QMessageBox.warning(
                self, "Backup",
                "Модуль core/backup.py не найден."
            )
            return

        path, error = create_backup()

        if path:
            QMessageBox.information(
                self, "Backup",
                f"Backup создан:\n{path}"
            )
        else:
            QMessageBox.warning(self, "Backup", f"Ошибка: {error}")

    def _show_my_id(self):
        text = (
            f"═══ МОЙ NOCTURNE ID ═══\n\n"
            f"UUID:\n{self.identity.uuid}\n\n"
            f"Отпечаток:\n{self.identity.fingerprint}\n\n"
            f"Короткий ID:\n{self.identity.get_short_id()}\n\n"
        )

        if self.identity.onion_address:
            text += f"🧅 .onion-адрес:\n{self.identity.onion_address}\n\n"
            text += "Передай .onion собеседнику для подключения."
        else:
            text += "🧅 Tor ещё не запущен"

        QMessageBox.information(self, "Мой ID", text)

    def _show_settings(self):
        try:
            from widgets.settings_widget import SettingsDialog
        except ImportError:
            QMessageBox.warning(
                self, "Настройки",
                "Модуль widgets/settings_widget.py не найден."
            )
            return

        dlg = SettingsDialog(self.settings, self)
        dlg.exec()

    def _show_about(self):
        QMessageBox.about(
            self, "О NOCTURNE",
            "<h2 style='color:#b040ff;'>🦇 NOCTURNE v0.2</h2>"
            "<p>Анонимный P2P-мессенджер через Tor</p>"
            "<p style='color:#888;'>"
            "• X25519 + AES-256-GCM<br>"
            "• Файлы, группы, очередь<br>"
            "• Никаких серверов<br>"
            "• Скрытые .onion-сервисы<br>"
            "• E2E-шифрование"
            "</p>"
            "<p style='color:#444; font-size:9pt;'>"
            "github.com/Felolen/nocturne</p>"
        )

    # ═══════════════════════════════════════════════════════
    # DRAG & DROP
    # ═══════════════════════════════════════════════════════

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self.current_contact:
            return

        files = [u.toLocalFile() for u in event.mimeData().urls()]

        for f in files:
            if Path(f).is_file():
                self._send_file(f)

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