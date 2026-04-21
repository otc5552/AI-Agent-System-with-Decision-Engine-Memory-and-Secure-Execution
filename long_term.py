"""
memory/long_term.py
════════════════════
Long-Term Memory — بيحفظ معلومات المستخدم بشكل دائم.
مع استرجاعها عند الحاجة.

التخزين: JSON file (بسيط، بدون dependencies خارجية)

الاستخدام:
    ltm = LongTermMemory("memory/user_data.json")
    ltm.store("name", "مصطفى")
    ltm.store("project", "PeacockAgent")
    name = ltm.recall("name")  # → "مصطفى"
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── أنماط الاستخراج التلقائي من المحادثة ─────────────────────
_EXTRACT_PATTERNS: List[Tuple[str, str]] = [
    # اسم المستخدم
    (r"(?:اسمي|أنا اسمي|my name is|I(?:'m| am) called)\s+([A-Za-zأ-ي]+(?:\s+[A-Za-zأ-ي]+)?)", "name"),
    # المشروع
    (r"(?:بشتغل على|أعمل على|working on|project is|مشروعي)\s+(.+?)(?:\.|,|$)", "current_project"),
    # اللغة المفضّلة
    (r"(?:لغتي المفضلة|أفضّل|prefer|use)\s+(Python|JavaScript|Java|C\+\+|Rust|Go|TypeScript)", "preferred_language"),
    # نظام التشغيل
    (r"\b(Windows|Linux|Mac|macOS|Ubuntu)\b", "os"),
]


class LongTermMemory:
    """
    ذاكرة طويلة المدى — تحفظ معلومات المستخدم بشكل دائم.

    Features:
      • تخزين key-value مع timestamp
      • استخراج تلقائي من المحادثة
      • البحث بالكلمة المفتاحية
      • تصدير واستيراد JSON
    """

    def __init__(self, storage_path: str = "data/long_term_memory.json"):
        self._path = Path(storage_path)
        self._data: Dict[str, Dict] = {}
        self._load()

    # ── تخزين ─────────────────────────────────────────────────

    def store(self, key: str, value: Any, category: str = "general"):
        """يحفظ معلومة"""
        self._data[key] = {
            "value":     value,
            "category":  category,
            "timestamp": datetime.now().isoformat(),
            "access_count": self._data.get(key, {}).get("access_count", 0),
        }
        self._save()

    def store_many(self, items: Dict[str, Any], category: str = "general"):
        """يحفظ مجموعة معلومات دفعة واحدة"""
        for k, v in items.items():
            self.store(k, v, category)

    # ── استرجاع ────────────────────────────────────────────────

    def recall(self, key: str, default=None) -> Any:
        """يسترجع معلومة بالمفتاح"""
        entry = self._data.get(key)
        if entry:
            entry["access_count"] = entry.get("access_count", 0) + 1
            self._save()
            return entry["value"]
        return default

    def recall_all(self, category: str = None) -> Dict[str, Any]:
        """يسترجع كل المعلومات (أو من category معينة)"""
        result = {}
        for key, entry in self._data.items():
            if category is None or entry.get("category") == category:
                result[key] = entry["value"]
        return result

    def search(self, keyword: str) -> Dict[str, Any]:
        """يبحث عن keyword في المفاتيح والقيم"""
        kw = keyword.lower()
        result = {}
        for key, entry in self._data.items():
            val_str = str(entry.get("value", "")).lower()
            if kw in key.lower() or kw in val_str:
                result[key] = entry["value"]
        return result

    # ── استخراج تلقائي من المحادثة ────────────────────────────

    def extract_from_text(self, text: str) -> Dict[str, str]:
        """
        يستخرج معلومات تلقائياً من نص المحادثة.
        يحفظها ويرجع ما استخرجه.
        """
        extracted = {}
        for pattern, key in _EXTRACT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    self.store(key, value, category="auto_extracted")
                    extracted[key] = value
        return extracted

    # ── حذف ────────────────────────────────────────────────────

    def forget(self, key: str) -> bool:
        """يحذف معلومة"""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def forget_category(self, category: str):
        """يحذف كل معلومات category معينة"""
        keys_to_del = [k for k, v in self._data.items()
                       if v.get("category") == category]
        for k in keys_to_del:
            del self._data[k]
        self._save()

    def clear(self):
        """يمسح كل الذاكرة"""
        self._data.clear()
        self._save()

    # ── معلومات ────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._data)

    def get_summary_text(self) -> str:
        """ملخص نصي للذاكرة — للـ context builder"""
        if not self._data:
            return ""
        lines = ["[معلومات المستخدم المحفوظة]:"]
        for key, entry in sorted(self._data.items()):
            lines.append(f"  • {key}: {entry['value']}")
        return "\n".join(lines)

    # ── تخزين ملف ─────────────────────────────────────────────

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load(self):
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {}

    def export_json(self) -> str:
        """تصدير الذاكرة كـ JSON string"""
        return json.dumps(self._data, ensure_ascii=False, indent=2)

    def import_json(self, json_str: str):
        """استيراد ذاكرة من JSON string"""
        try:
            self._data = json.loads(json_str)
            self._save()
        except Exception as e:
            raise ValueError(f"Invalid JSON: {e}")
