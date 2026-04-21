"""
router/intent_detector.py
══════════════════════════
Intent Detector — بيفهم نية المستخدم من النص.

الأنواع:
  CODE     → كتابة / شرح / تصحيح كود
  SEARCH   → بحث على الإنترنت
  EXECUTE  → تنفيذ أمر / فتح برنامج / تحكم
  FILE     → تعامل مع ملفات
  CREATE   → إنشاء مستند / صورة / عرض
  CHAT     → محادثة عامة / أسئلة
  MEMORY   → "تذكر" / "احفظ" / "نسيت"
  PLAN     → مهام متعددة / خطوات

الاستخدام:
    detector = IntentDetector()
    intent   = detector.detect("اكتب كود Python لفرز قائمة")
    # → Intent.CODE
"""

import re
from enum import Enum
from typing import Dict, List, Tuple


class Intent(Enum):
    CODE    = "code"
    SEARCH  = "search"
    EXECUTE = "execute"
    FILE    = "file"
    CREATE  = "create"
    CHAT    = "chat"
    MEMORY  = "memory"
    PLAN    = "plan"


# ── كلمات مفتاحية لكل intent ─────────────────────────────────
_PATTERNS: Dict[Intent, List[str]] = {

    Intent.CODE: [
        r"\b(كود|code|برمجة|script|function|class|def\s|import\s)",
        r"\b(python|javascript|java|c\+\+|rust|kotlin|swift)\b",
        r"\b(اكتب|write|implement|create)\b.+\b(function|method|class|algorithm)\b",
        r"\b(debug|fix|error|bug|exception|خطأ|صلّح)\b",
        r"\b(compile|run|execute)\b.+\b(code|script)\b",
        r"```",
    ],

    Intent.SEARCH: [
        r"\b(ابحث|search|find|اوجد|دور)\b",
        r"\b(ما هو|what is|من هو|who is|متى|when|أين|where)\b",
        r"\b(آخر أخبار|latest|recent|news|أحدث)\b",
        r"\b(سعر|price|كم سعر|how much)\b",
        r"\b(google|دوك|duckduckgo)\b",
    ],

    Intent.EXECUTE: [
        r"\b(افتح|open|شغّل|run|launch|start)\b",
        r"\b(اقفل|close|أوقف|stop|kill)\b",
        r"\b(اضغط|click|انقر|اكتب|type|اسكرول|scroll)\b",
        r"\b(screenshot|لقطة شاشة|صورة الشاشة)\b",
        r"\b(cmd|terminal|command|أمر)\b",
        r"\b(install|pip install|تثبيت)\b",
    ],

    Intent.FILE: [
        r"\b(ملف|file|folder|مجلد|directory)\b",
        r"\b(اقرأ|read|افتح|open|اعرض|show)\b.+\b(file|ملف)\b",
        r"\b(احذف|delete|remove|امسح)\b",
        r"\b(انسخ|copy|انقل|move|rename)\b",
        r"\b(list|عرض محتويات|محتوى المجلد)\b",
        r"\b(اكتب في|write to|save|احفظ)\b.+\b(file|ملف)\b",
    ],

    Intent.CREATE: [
        r"\b(انشئ|create|اعمل|اصنع|generate)\b",
        r"\b(word|docx|document|مستند|تقرير|report)\b",
        r"\b(powerpoint|pptx|عرض|presentation)\b",
        r"\b(pdf|بي دي إف)\b",
        r"\b(صورة|image|picture|رسم|draw)\b.+\b(إنشاء|create|generate)\b",
        r"\b(generate|generate image|توليد صورة)\b",
    ],

    Intent.MEMORY: [
        r"\b(تذكر|remember|احفظ|save)\b.+\b(معلومة|info|that)\b",
        r"\b(نسيت|forgot|remind me|ذكّرني)\b",
        r"\b(اسمي|my name is|أنا اسمي)\b",
        r"\b(في المرة اللي فاتت|last time|سابقاً|previously)\b",
        r"\b(ما قلته|what I said|ذاكرتك|your memory)\b",
    ],

    Intent.PLAN: [
        r"\b(خطوات|steps|plan|خطة|خطوة بخطوة)\b",
        r"\b(أولاً.*ثانياً|first.*then|ثم|after that)\b",
        r"\b(مهام متعددة|multiple tasks|سلسلة|series)\b",
        r"\b(تلقائياً|automatically|auto|بشكل تلقائي)\b",
        r"\b(اعمل.*و.*و|do.*and.*and)\b",
    ],
}

# ── أولوية الـ intents (لما يتطابق أكتر من واحد) ─────────────
_PRIORITY = [
    Intent.PLAN,
    Intent.CODE,
    Intent.CREATE,
    Intent.EXECUTE,
    Intent.FILE,
    Intent.SEARCH,
    Intent.MEMORY,
    Intent.CHAT,
]


class IntentDetector:
    """
    بيكتشف نية المستخدم من النص.
    بيرجع (intent, confidence, matched_patterns).
    """

    def detect(self, text: str) -> Tuple[Intent, float, List[str]]:
        """
        يكتشف الـ intent الأساسي.
        Returns (intent, confidence 0-1, matched_patterns)
        """
        text_lower = text.lower().strip()

        scores: Dict[Intent, int] = {i: 0 for i in Intent}
        matched: Dict[Intent, List[str]] = {i: [] for i in Intent}

        for intent, patterns in _PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[intent] += 1
                    matched[intent].append(pattern)

        # لو مفيش تطابق → CHAT
        if all(s == 0 for s in scores.values()):
            return Intent.CHAT, 0.5, []

        # اختار الأعلى score مع مراعاة الأولوية
        best_intent = Intent.CHAT
        best_score  = 0

        for intent in _PRIORITY:
            if scores[intent] > best_score:
                best_score  = scores[intent]
                best_intent = intent

        # حساب confidence
        total_patterns = sum(len(p) for p in _PATTERNS.values())
        confidence = min(1.0, best_score / 3)

        return best_intent, confidence, matched[best_intent]

    def detect_all(self, text: str) -> Dict[Intent, int]:
        """يرجع scores كل الـ intents (للـ debugging)"""
        scores = {i: 0 for i in Intent}
        for intent, patterns in _PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    scores[intent] += 1
        return scores

    def is_multi_step(self, text: str) -> bool:
        """هل الطلب يحتاج خطوات متعددة؟"""
        multi_indicators = [
            r"\b(ثم|then|بعد ذلك|after|و بعدين|and then)\b",
            r"\b(أولاً|first|ثانياً|second|ثالثاً|third)\b",
            r"\d+\.\s+\w+",           # numbered list
            r"[-•]\s+\w+.*\n[-•]\s+", # bullet points
        ]
        for pattern in multi_indicators:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                return True
        return False
