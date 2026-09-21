from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton,
    QLineEdit, QTextEdit, QDialog, QDialogButtonBox,
    QCheckBox, QScrollArea, QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from core.storage import ContactStore


class CreateGroupDialog(QDialog):
    """Диалог создания группы."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Создать группу")
        self.setMinimumSize(500, 500)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        self.selected_uuids = []

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # название группы
        title = QLabel("НАЗВАНИЕ ГРУППЫ")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Например: Ночные кодеры")
        layout.addWidget(self.name_input)

        # участники
        members_title = QLabel("УЧАСТНИКИ")
        members_title.setObjectName("SectionTitle")
        layout.addWidget(members_title)

        info = QLabel("Выбери контактов для добавления в группу:")
        info.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(info)

        # список контактов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.members_layout = QVBoxLayout(container)
        self.members_layout.setSpacing(8)

        self.member_checkboxes = {}

        store = ContactStore()
        contacts = store.list_all()

        if not contacts:
            empty = QLabel("Нет контактов для добавления")
            empty.setStyleSheet("color: #444; padding: 20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.members_layout.addWidget(empty)
        else:
            for c in contacts:
                uuid = c["uuid"]
                nickname = c.get("nickname", "unknown")
                fp = c.get("fingerprint", "")[:16]

                row = QFrame()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(10, 6, 10, 6)

                cb = QCheckBox()
                cb.setProperty("uuid", uuid)

                label = QLabel(f"👤  {nickname}")
                label.setStyleSheet("color: #d4d4d4; font-size: 10pt;")

                fp_label = QLabel(fp)
                fp_label.setStyleSheet("color: #666; font-size: 8pt;")

                row_layout.addWidget(cb)
                row_layout.addWidget(label)
                row_layout.addStretch()
                row_layout.addWidget(fp_label)

                self.member_checkboxes[uuid] = cb
                self.members_layout.addWidget(row)

        self.members_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # кнопки
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        name = self.name_input.text().strip()

        selected = [
            uuid for uuid, cb in self.member_checkboxes.items()
            if cb.isChecked()
        ]

        return {
            "name": name,
            "members": selected,
        }


class GroupChatWidget(QWidget):
    """Виджет группового чата."""

    message_sent = pyqtSignal(str, str)  # group_id, text

    def __init__(self, group, identity, parent=None):
        super().__init__(parent)

        self.group = group
        self.identity = identity

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # заголовок
        header = QHBoxLayout()

        self.title_label = QLabel(f"👥 {self.group.name}")
        self.title_label.setObjectName("SectionTitle")
        header.addWidget(self.title_label)

        header.addStretch()

        self.members_count = QLabel(f"{self.group.member_count()} участников")
        self.members_count.setStyleSheet("color: #888; font-size: 9pt;")
        header.addWidget(self.members_count)

        layout.addLayout(header)

        # список участников
        self.members_label = QLabel("")
        self.members_label.setStyleSheet("color: #666; font-size: 8pt;")
        self.members_label.setWordWrap(True)
        layout.addWidget(self.members_label)

        # область сообщений
        self.chat_view = QTextEdit()
        self.chat_view.setObjectName("ChatView")
        self.chat_view.setReadOnly(True)
        layout.addWidget(self.chat_view, 1)

        # ввод
        input_layout = QHBoxLayout()

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Напиши сообщение в группу...")
        self.message_input.returnPressed.connect(self._send)
        input_layout.addWidget(self.message_input, 1)

        send_btn = QPushButton("Отправить 🦇")
        send_btn.clicked.connect(self._send)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)

    def refresh(self):
        """Обновляет отображение."""
        self.members_count.setText(f"{self.group.member_count()} участников")

        # список участников
        names = []
        for uuid, data in self.group.members.items():
            nickname = data.get("nickname", "unknown")
            role = data.get("role", "member")
            if role == "admin":
                names.append(f"👑 {nickname}")
            else:
                names.append(nickname)

        self.members_label.setText("  ·  ".join(names))

        # сообщения
        self._load_messages()

    def _load_messages(self):
        self.chat_view.clear()

        messages = self.group.messages[-200:]

        if not messages:
            self.chat_view.setHtml(
                "<div style='color:#444; text-align:center; padding:40px;'>"
                "🦇 Начало группового чата<br><br>"
                "<span style='font-size:9pt;'>"
                "Сообщения защищены E2E-шифрованием"
                "</span></div>"
            )
            return

        html_parts = []

        for m in messages:
            sender_uuid = m.get("sender_uuid", "")
            text = m.get("text", "").replace("<", "&lt;").replace(">", "&gt;")
            ts = m.get("timestamp", "")[:19].replace("T", " ")

            # имя отправителя
            member = self.group.members.get(sender_uuid, {})
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

        scrollbar = self.chat_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _send(self):
        text = self.message_input.text().strip()
        if not text:
            return

        self.message_sent.emit(self.group.group_id, text)
        self.message_input.clear()