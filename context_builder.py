"""
memory/context_builder.py
══════════════════════════
Context Builder — بيبني prompt ذكي من:
  • المحادثة الحالية (ShortTermMemory)
  • معلومات المستخدم (LongTermMemory)
  • المعرفة ذات الصلة (VectorMemory)
  • السياق الحالي (current_context)

الاستخدام:
    builder  = ContextBuilder(stm, ltm, vm)
    messages = builder.build(user_input)
"""

from typing import List, Dict, Optional

from .short_term  import ShortTermMemory
from .long_term   import LongTermMemory
from .vector_mem  import VectorMemory


class ContextBuilder:
    """
    بيجمع كل مصادر الذاكرة في messages list جاهزة للـ LLM.

    الترتيب النهائي:
      1. System prompt (مع معلومات المستخدم)
      2. ملخص المحادثة القديمة (لو موجود)
      3. معرفة ذات صلة من VectorMemory
      4. المحادثة الحالية (ShortTermMemory)
      5. رسالة المستخدم الجديدة
    """

    def __init__(
        self,
        short_term:     ShortTermMemory,
        long_term:      LongTermMemory,
        vector_memory:  VectorMemory,
        system_prompt:  str = "",
    ):
        self.stm    = short_term
        self.ltm    = long_term
        self.vm     = vector_memory
        self._sys   = system_prompt

        # سياق إضافي (نتيجة tool مثلاً)
        self._current_context: str = ""

    # ── بناء الـ messages ─────────────────────────────────────

    def build(
        self,
        user_input:    str,
        include_vm:    bool = True,
        vm_top_k:      int  = 3,
        include_ltm:   bool = True,
    ) -> List[Dict]:
        """
        يبني messages list كاملة جاهزة للـ LLM.
        """
        messages = []

        # 1. System Message
        system_content = self._build_system(include_ltm)
        if system_content:
            messages.append({"role": "system", "content": system_content})

        # 2. ملخص المحادثة القديمة
        if self.stm.has_summary:
            messages.append({
                "role":    "system",
                "content": f"[ملخص المحادثة السابقة]:\n{self.stm.summary}"
            })

        # 3. معرفة ذات صلة من VectorMemory
        if include_vm and user_input:
            vm_text = self.vm.search_text(user_input, top_k=vm_top_k)
            if vm_text:
                messages.append({
                    "role":    "system",
                    "content": vm_text
                })

        # 4. سياق إضافي (tool result / current context)
        if self._current_context:
            messages.append({
                "role":    "system",
                "content": f"[السياق الحالي]:\n{self._current_context}"
            })

        # 5. المحادثة الحالية
        for msg in self.stm.get_messages(include_summary=False):
            messages.append(msg)

        # 6. رسالة المستخدم الجديدة
        if user_input:
            messages.append({"role": "user", "content": user_input})

        return messages

    def _build_system(self, include_ltm: bool) -> str:
        """يبني system prompt مع معلومات المستخدم"""
        parts = []

        if self._sys:
            parts.append(self._sys)

        # معلومات المستخدم من LongTermMemory
        if include_ltm:
            ltm_text = self.ltm.get_summary_text()
            if ltm_text:
                parts.append(ltm_text)

        return "\n\n".join(parts) if parts else ""

    # ── إدارة الـ Context ─────────────────────────────────────

    def set_context(self, context: str):
        """يضيف سياق مؤقت (مثلاً نتيجة tool)"""
        self._current_context = context

    def clear_context(self):
        self._current_context = ""

    def set_system_prompt(self, prompt: str):
        self._sys = prompt

    # ── تسجيل المحادثة ────────────────────────────────────────

    def add_user(self, text: str):
        """يضيف رسالة مستخدم للذاكرة القصيرة"""
        self.stm.add("user", text)
        # استخراج معلومات تلقائي من رسالة المستخدم
        extracted = self.ltm.extract_from_text(text)
        if extracted:
            pass  # يمكن إضافة callback هنا

    def add_assistant(self, text: str):
        """يضيف رد المساعد للذاكرة القصيرة"""
        self.stm.add("assistant", text)

    def add_tool_result(self, tool_name: str, result: str):
        """
        يضيف نتيجة tool للذاكرة.
        • نتيجة بحث → VectorMemory
        • نتيجة أداة → سياق مؤقت
        """
        if tool_name == "search_web":
            self.vm.add(result[:1000], tags=["search"], source="web")
        elif tool_name == "read_file":
            self.vm.add(result[:2000], tags=["file"], source="file")
        else:
            self.set_context(f"[نتيجة {tool_name}]:\n{result[:500]}")

    # ── معلومات ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "short_term_turns": self.stm.turn_count,
            "has_summary":      self.stm.has_summary,
            "long_term_keys":   self.ltm.size,
            "vector_chunks":    self.vm.size,
        }

    def clear_session(self):
        """مسح المحادثة الحالية (بدون مسح الذاكرة الطويلة)"""
        self.stm.clear()
        self._current_context = ""
