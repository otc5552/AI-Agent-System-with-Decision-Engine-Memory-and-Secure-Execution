"""
router/decision_engine.py
══════════════════════════
Decision Engine — بيقرر أفضل طريقة تنفيذ:
  • LLM Only    → سؤال / محادثة / كود
  • Tool Only   → بحث / ملفات / تحكم
  • Hybrid      → LLM يخطط + Tools تنفّذ
  • Plan        → خطوات متعددة

الاستخدام:
    engine  = DecisionEngine()
    mode    = engine.decide(intent, text)
    # → "llm" / "tool" / "hybrid" / "plan"
"""

from dataclasses import dataclass
from typing import Dict
from .intent_detector import Intent


@dataclass
class Decision:
    mode:       str    # "llm" / "tool" / "hybrid" / "plan"
    reasoning:  str    # سبب القرار
    confidence: float  # 0-1


# ── قواعد التوجيه الثابتة ────────────────────────────────────
_INTENT_TO_MODE: Dict[Intent, str] = {
    Intent.CHAT:    "llm",
    Intent.CODE:    "llm",      # LLM يكتب الكود
    Intent.MEMORY:  "llm",      # Memory System + LLM
    Intent.SEARCH:  "tool",     # search_web مباشرة
    Intent.FILE:    "hybrid",   # LLM يقرر + Tool تنفّذ
    Intent.CREATE:  "hybrid",   # LLM يولّد المحتوى + Tool تحفظ
    Intent.EXECUTE: "hybrid",   # LLM يحدد الأداة + Tool تشغّل
    Intent.PLAN:    "plan",     # MultiStepPlanner
}

_REASONING: Dict[str, str] = {
    "llm":    "✨ LLM يجيب مباشرة — لا يحتاج أدوات",
    "tool":   "🔧 أداة مباشرة — أسرع وأدق من LLM",
    "hybrid": "🔄 LLM يخطط + أداة تنفّذ",
    "plan":   "📋 خطوات متعددة — MultiStepPlanner",
}


class DecisionEngine:
    """
    بيقرر أفضل طريقة تنفيذ للطلب.

    يأخذ في الاعتبار:
      • الـ Intent
      • طول النص
      • وجود tool calls في الـ context
      • إعدادات المستخدم
    """

    def __init__(self, prefer_tool: bool = False):
        """
        prefer_tool: لو True → يفضّل الـ tools على LLM لما ينفع
        """
        self.prefer_tool = prefer_tool

        # Hook للقرارات المخصصة
        # signature: (intent, text) -> str | None
        self._custom_rule = None

    def decide(self, intent: Intent, text: str, context: list = None) -> Decision:
        """
        يقرر طريقة التنفيذ.
        Returns Decision(mode, reasoning, confidence)
        """
        # 1. Custom Rule Hook
        if self._custom_rule:
            custom = self._custom_rule(intent, text)
            if custom:
                return Decision(custom, "🔧 Custom rule applied", 1.0)

        # 2. القاعدة الأساسية
        mode = _INTENT_TO_MODE.get(intent, "llm")

        # 3. تعديلات بناءً على السياق
        mode, confidence = self._adjust(mode, intent, text, context or [])

        return Decision(mode, _REASONING.get(mode, ""), confidence)

    def _adjust(self, mode: str, intent: Intent, text: str, context: list):
        """تعديل القرار بناءً على السياق"""
        confidence = 0.85

        # نص قصير جداً → LLM مباشرة
        if len(text.strip()) < 10:
            return "llm", 0.7

        # لو السياق عنده tool calls → hybrid
        if any("tool_calls" in m for m in context):
            if mode == "llm":
                mode = "hybrid"
                confidence = 0.75

        # SEARCH طويل → hybrid (LLM يلخّص)
        if intent == Intent.SEARCH and len(text) > 100:
            mode = "hybrid"
            confidence = 0.8

        return mode, confidence

    def register_custom_rule(self, fn):
        """
        Hook لإضافة قواعد مخصصة.
        fn(intent, text) → "llm"|"tool"|"hybrid"|"plan"|None
        """
        self._custom_rule = fn

    def explain(self, intent: Intent, text: str) -> str:
        """شرح القرار للـ debugging"""
        dec = self.decide(intent, text)
        return (
            f"Intent: {intent.value}\n"
            f"Mode:   {dec.mode}\n"
            f"Reason: {dec.reasoning}\n"
            f"Conf:   {dec.confidence:.0%}"
        )
