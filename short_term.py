"""
memory/short_term.py
═════════════════════
Short-Term Memory — بيحفظ سياق المحادثة الحالية.
مع تلخيص تلقائي لما المحادثة تطول.

الاستخدام:
    stm = ShortTermMemory(max_turns=20)
    stm.add("user", "مرحبا")
    stm.add("assistant", "أهلاً!")
    messages = stm.get_messages()
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable
from datetime import datetime


@dataclass
class Turn:
    role:      str       # "user" / "assistant" / "system"
    content:   str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata:  Dict = field(default_factory=dict)


class ShortTermMemory:
    """
    ذاكرة قصيرة المدى — سياق المحادثة الحالية.

    Features:
      • حد أقصى للعدد (max_turns)
      • تلخيص تلقائي لما تكبر (via LLM hook)
      • البحث في السياق الحالي
    """

    def __init__(
        self,
        max_turns:    int = 20,
        summarize_at: int = 15,            # ابدأ التلخيص عند كذا turn
        summarize_fn: Optional[Callable] = None,  # LLM summarizer hook
    ):
        self.max_turns    = max_turns
        self.summarize_at = summarize_at
        self._summarize   = summarize_fn
        self._turns: List[Turn] = []
        self._summary: str = ""            # ملخص المحادثة القديمة

    # ── إضافة رسالة ───────────────────────────────────────────

    def add(self, role: str, content: str, metadata: Dict = None):
        """يضيف رسالة جديدة للذاكرة"""
        turn = Turn(role=role, content=content, metadata=metadata or {})
        self._turns.append(turn)

        # تلخيص تلقائي لو وصلنا للحد
        if len(self._turns) >= self.summarize_at and self._summarize:
            self._auto_summarize()

        # قص الزيادة
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def add_system(self, content: str):
        """رسالة system"""
        self.add("system", content)

    # ── جلب الرسائل ────────────────────────────────────────────

    def get_messages(self, include_summary: bool = True) -> List[Dict]:
        """
        يرجع المحادثة كـ list من messages للـ LLM.
        لو فيه ملخص → يُضاف في الأول.
        """
        messages = []

        if include_summary and self._summary:
            messages.append({
                "role": "system",
                "content": f"[ملخص المحادثة السابقة]:\n{self._summary}"
            })

        for turn in self._turns:
            messages.append({
                "role":    turn.role,
                "content": turn.content,
            })

        return messages

    def get_last_n(self, n: int) -> List[Dict]:
        """آخر N رسالة"""
        return [{"role": t.role, "content": t.content}
                for t in self._turns[-n:]]

    # ── تلخيص ─────────────────────────────────────────────────

    def _auto_summarize(self):
        """يلخّص النصف الأول من المحادثة"""
        half = len(self._turns) // 2
        to_summarize = self._turns[:half]

        text = "\n".join(f"{t.role}: {t.content}" for t in to_summarize)

        try:
            new_summary = self._summarize(text)
            if new_summary:
                # دمج الملخص القديم مع الجديد
                self._summary = (
                    f"{self._summary}\n{new_summary}" if self._summary
                    else new_summary
                )
                # احذف الـ turns المُلخَّصة
                self._turns = self._turns[half:]
        except Exception:
            # لو فشل التلخيص — احذف القديمة فقط
            self._turns = self._turns[half:]

    def set_summarizer(self, fn: Callable):
        """ربط LLM summarizer hook"""
        self._summarize = fn

    # ── معلومات ───────────────────────────────────────────────

    def clear(self):
        self._turns.clear()
        self._summary = ""

    def reset_summary(self):
        self._summary = ""

    @property
    def turn_count(self) -> int:
        return len(self._turns)

    @property
    def has_summary(self) -> bool:
        return bool(self._summary)

    @property
    def summary(self) -> str:
        return self._summary

    def search(self, keyword: str) -> List[Turn]:
        """يبحث في المحادثة عن كلمة"""
        return [t for t in self._turns
                if keyword.lower() in t.content.lower()]

    def last_user_message(self) -> Optional[str]:
        """آخر رسالة من المستخدم"""
        for turn in reversed(self._turns):
            if turn.role == "user":
                return turn.content
        return None
