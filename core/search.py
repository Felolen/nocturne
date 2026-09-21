from datetime import datetime
from collections import defaultdict


class MessageSearch:
    """Поиск по сообщениям."""

    def __init__(self, storage, group_manager=None):
        self.storage = storage
        self.group_manager = group_manager

    def search_in_contact(self, contact_uuid, query, case_sensitive=False):
        """Поиск по сообщениям с контактом."""
        messages = self.storage.get_messages(contact_uuid, limit=10000)

        return self._filter_messages(messages, query, case_sensitive)

    def search_all(self, query, case_sensitive=False, limit=200):
        """Поиск по всем чатам."""
        results = []

        conversations = self.storage.get_conversations()

        for uuid in conversations:
            messages = self.storage.get_messages(uuid, limit=5000)
            found = self._filter_messages(messages, query, case_sensitive)

            for m in found:
                m["contact_uuid"] = uuid
                results.append(m)

            if len(results) >= limit:
                break

        # сортируем по времени
        results.sort(key=lambda m: m.get("timestamp", ""), reverse=True)

        return results[:limit]

    def search_in_groups(self, query, case_sensitive=False, limit=100):
        """Поиск по групповым сообщениям."""
        if not self.group_manager:
            return []

        results = []

        for group in self.group_manager.list_groups():
            messages = group.messages

            for m in messages:
                text = m.get("text", "")
                target = text if case_sensitive else text.lower()
                q = query if case_sensitive else query.lower()

                if q in target:
                    results.append({
                        "group_id": group.group_id,
                        "group_name": group.name,
                        "msg_id": m.get("msg_id"),
                        "sender_uuid": m.get("sender_uuid"),
                        "text": text,
                        "timestamp": m.get("timestamp"),
                    })

            if len(results) >= limit:
                break

        results.sort(key=lambda m: m.get("timestamp", ""), reverse=True)

        return results[:limit]

    def search_everywhere(self, query, case_sensitive=False):
        """Поиск везде — и в личных, и в группах."""
        personal = self.search_all(query, case_sensitive)
        groups = self.search_in_groups(query, case_sensitive)

        return {
            "personal": personal,
            "groups": groups,
            "total": len(personal) + len(groups),
        }

    def _filter_messages(self, messages, query, case_sensitive=False):
        """Фильтрует список сообщений по запросу."""
        if not query:
            return messages

        result = []
        q = query if case_sensitive else query.lower()

        for m in messages:
            text = m.get("text", "")
            target = text if case_sensitive else text.lower()

            if q in target:
                result.append(m)

        return result

    def highlight(self, text, query, tag_start="<<", tag_end=">>"):
        """Подсвечивает совпадения в тексте."""
        if not query:
            return text

        text_lower = text.lower()
        query_lower = query.lower()

        result = []
        i = 0
        while i < len(text):
            pos = text_lower.find(query_lower, i)
            if pos == -1:
                result.append(text[i:])
                break

            result.append(text[i:pos])
            result.append(tag_start + text[pos:pos + len(query)] + tag_end)
            i = pos + len(query)

        return "".join(result)


class ContactSearch:
    """Поиск контактов."""

    def __init__(self, contact_getter):
        self.get_contacts = contact_getter

    def search(self, query, case_sensitive=False):
        """Поиск по нику / fingerprint / uuid."""
        if not query:
            return self.get_contacts()

        contacts = self.get_contacts()
        result = []

        q = query if case_sensitive else query.lower()

        for c in contacts:
            nickname = c.get("nickname", "")
            fingerprint = c.get("fingerprint", "")
            uuid = c.get("uuid", "")
            onion = c.get("onion_address", "")

            haystack = f"{nickname} {fingerprint} {uuid} {onion}"
            if not case_sensitive:
                haystack = haystack.lower()

            if q in haystack:
                result.append(c)

        return result

    def filter_online(self, contacts, online_getter):
        """Оставляет только онлайн."""
        return [c for c in contacts if online_getter(c["uuid"])]

    def sort_by_name(self, contacts):
        """Сортировка по имени."""
        return sorted(
            contacts,
            key=lambda c: c.get("nickname", "").lower()
        )

    def sort_by_last_seen(self, contacts):
        """Сортировка по последнему визиту."""
        return sorted(
            contacts,
            key=lambda c: c.get("last_seen", ""),
            reverse=True,
        )