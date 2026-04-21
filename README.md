# PeacockAgent v2.0 — نظام ذكاء اصطناعي كامل
## هيكل المشروع

```
PeacockAgent/
│
├── agent.py              ← Orchestrator الرئيسي (نقطة الدخول)
├── main.py               ← تشغيل UI أو CLI
├── executor.py           ← الأدوات الفعلية (بدون تعديل)
├── llm_provider.py       ← LLM Provider المحدّث
│
├── security/             ← 🔒 نظام الأمان
│   ├── __init__.py
│   ├── permissions.py    ← صلاحيات كل أداة
│   ├── risk_analyzer.py  ← تصنيف الأوامر (SAFE/MEDIUM/DANGER)
│   ├── validator.py      ← فلترة المدخلات
│   ├── sandbox.py        ← بيئة التنفيذ الآمنة
│   └── logger.py         ← تسجيل العمليات
│
├── router/               ← 🧠 نظام التوجيه الذكي
│   ├── __init__.py
│   ├── intent_detector.py ← كشف نية المستخدم
│   ├── decision_engine.py ← قرار LLM/Tool/Hybrid
│   ├── task_router.py    ← توجيه الطلب
│   └── planner.py        ← تخطيط متعدد الخطوات
│
├── memory/               ← 💾 نظام الذاكرة
│   ├── __init__.py
│   ├── short_term.py     ← ذاكرة المحادثة الحالية
│   ├── long_term.py      ← ذاكرة المستخدم الدائمة
│   ├── vector_mem.py     ← RAG بسيط (TF-IDF)
│   └── context_builder.py ← بناء الـ prompt الذكي
│
└── data/                 ← بيانات محفوظة
    ├── long_term.json
    ├── vector_memory.json
    └── security.log
```

## الاستخدام السريع

```python
from agent import PeacockAgent

agent = PeacockAgent(api_key="gsk_...")

# محادثة عادية
reply = agent.chat("افتح Chrome")

# حفظ معلومة
agent.remember("اسمي", "مصطفى")

# بحث في الذاكرة
result = agent.search_memory("Python")

# حالة النظام
print(agent.diagnostics())
```

## التشغيل

```bash
# CLI
python main.py --cli --api-key gsk_...

# أو مع UI
python main.py --api-key gsk_...

# أو متغير بيئة
export GROQ_API_KEY=gsk_...
python main.py --cli
```

## Hooks للتوسيع

```python
# تأكيد العمليات الحساسة
agent.on_tool_confirm = lambda tool, risk, reason: my_dialog(...)

# إشعار بعد كل خطوة في الخطط
agent.on_step_done = lambda step: update_progress_bar(step)

# استقبال ردود LLM
agent.on_llm_response = lambda text: update_chat_ui(text)

# قواعد routing مخصصة
agent.add_router_rule(lambda intent, text: "tool" if "اسحب" in text else None)
```

## Pipeline كل طلب

```
User Input
    ↓
[Validator] فلترة المدخل
    ↓
[IntentDetector] كشف النية
    ↓
[ContextBuilder] بناء السياق (STM + LTM + VM)
    ↓
[DecisionEngine] قرار التوجيه
    ↓
[TaskRouter] → LLM / Tool / Hybrid / Plan
    ↓
[SandboxExecutor] تنفيذ آمن (لكل tool call)
    │   ├── InputValidator
    │   ├── RiskAnalyzer (SAFE/MEDIUM/DANGER)
    │   ├── PermissionSystem
    │   └── executor.dispatch_tool()
    ↓
[ContextBuilder] تحديث الذاكرة
    ↓
Response → User
```
