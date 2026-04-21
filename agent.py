"""
peacock/agent.py — PeacockAgent Orchestrator
═════════════════════════════════════════════
النقطة المركزية اللي بتجمع كل الأنظمة الثلاثة:

  🔒 Security Layer  (security/)
     └── SandboxExecutor → Validator → RiskAnalyzer → Permissions → Logger

  🧠 Router / Orchestrator  (router/)
     └── IntentDetector → DecisionEngine → TaskRouter → MultiStepPlanner

  💾 Memory System  (memory/)
     └── ShortTerm → LongTerm → VectorMemory → ContextBuilder

التكامل مع الكود الموجود:
  executor.py     → SandboxExecutor.dispatch
  llm_provider.py → TaskRouter._llm_chat

الاستخدام البسيط:
    agent = PeacockAgent(api_key="gsk_...")
    reply = agent.chat("افتح Chrome وابحث عن Python")

الاستخدام مع Hooks:
    agent.on_tool_confirm = lambda tool, risk, reason: ask_user(...)
    agent.on_step_done    = lambda step: update_ui(...)
    agent.on_blocked      = lambda tool, reason: show_warning(...)
"""

import os
from typing import Optional, Callable, List, Dict, Any

# ── الأنظمة الثلاثة ──────────────────────────────────────────
from security.sandbox     import SandboxExecutor
from security.permissions import PermissionSystem
from security.logger      import SecurityLogger
from security.risk_analyzer import RiskLevel

from router.intent_detector import IntentDetector, Intent
from router.decision_engine import DecisionEngine
from router.task_router     import TaskRouter, RouteResult
from router.planner         import MultiStepPlanner, Plan

from memory.short_term     import ShortTermMemory
from memory.long_term      import LongTermMemory
from memory.vector_mem     import VectorMemory
from memory.context_builder import ContextBuilder

# ── الكود الموجود ─────────────────────────────────────────────
from executor       import dispatch_tool as _raw_dispatch
from llm_provider   import LLMProvider


class PeacockAgent:
    """
    ══════════════════════════════════════════════════════
    PeacockAgent — نظام ذكاء اصطناعي كامل ذاتي الإدارة
    ══════════════════════════════════════════════════════

    المكونات:
      🔒 Security   — كل tool call يمر على Sandbox
      🧠 Router     — Intent Detection + Smart Routing
      💾 Memory     — Short/Long/Vector Memory + Context

    Hooks للتوسيع:
      on_tool_confirm(tool, risk, reason) → bool
      on_step_done(step) → None
      on_blocked(tool, reason) → None
      on_llm_response(content) → None
    """

    def __init__(
        self,
        # LLM Settings
        api_key:      str = "",
        provider:     str = "groq",
        model:        str = "llama-3.3-70b-versatile",
        ollama_url:   str = "http://localhost:11434",
        ollama_model: str = "llama3",

        # Memory Settings
        memory_dir:   str = "data",
        max_turns:    int = 20,

        # Security Settings
        log_file:     Optional[str] = None,
        verbose_logs: bool = False,

        # System Prompt
        system_prompt: str = "",
    ):
        # ── 1. LLM Provider ──────────────────────────────────
        self._llm = LLMProvider()
        self._llm.set_provider(
            provider,
            groq_api_key  = api_key,
            groq_model    = model,
            ollama_url    = ollama_url,
            ollama_model  = ollama_model,
        )

        # ── 2. Security Layer ─────────────────────────────────
        self._logger  = SecurityLogger(
            log_file = log_file,
            verbose  = verbose_logs,
        )
        self._perms   = PermissionSystem()
        self._sandbox = SandboxExecutor(
            executor_dispatch = _raw_dispatch,
            permission_system = self._perms,
            logger            = self._logger,
        )

        # ── 3. Memory System ──────────────────────────────────
        self._stm = ShortTermMemory(
            max_turns    = max_turns,
            summarize_at = max(10, max_turns - 5),
            summarize_fn = self._summarize_fn,
        )
        self._ltm = LongTermMemory(
            storage_path = os.path.join(memory_dir, "long_term.json")
        )
        self._vm  = VectorMemory(
            storage_path = os.path.join(memory_dir, "vector_memory.json")
        )
        self._ctx = ContextBuilder(
            short_term    = self._stm,
            long_term     = self._ltm,
            vector_memory = self._vm,
            system_prompt = system_prompt or self._default_system_prompt(),
        )

        # ── 4. Router / Orchestrator ───────────────────────────
        self._detector = IntentDetector()
        self._decision = DecisionEngine()
        self._router   = TaskRouter(
            llm_chat_fn    = self._llm_chat,
            sandbox_run_fn = self._sandbox.run,
            search_fn      = lambda q: self._sandbox.run("search_web", {"query": q}),
        )
        self._planner  = MultiStepPlanner(
            route_fn    = self._router.route,
            llm_chat_fn = self._llm_chat,
        )

        # ── 5. Hooks للتوسيع ──────────────────────────────────
        self.on_tool_confirm: Optional[Callable[[str, RiskLevel, str], bool]] = None
        self.on_step_done:    Optional[Callable]  = None
        self.on_blocked:      Optional[Callable]  = None
        self.on_llm_response: Optional[Callable]  = None

        # ربط الـ hooks بالأنظمة الداخلية
        self._sandbox.set_confirm_hook(self._confirm_tool)
        self._planner.set_step_hook(self._on_step_complete)

        # ── إحصائيات الجلسة ───────────────────────────────────
        self._total_requests = 0
        self._plans_created  = 0

    # ══════════════════════════════════════════════════════════
    #  نقطة الدخول الرئيسية
    # ══════════════════════════════════════════════════════════

    def chat(self, user_input: str) -> str:
        """
        المدخل الرئيسي — بيعالج أي طلب من المستخدم.

        Pipeline:
          1. Input Validation
          2. Intent Detection
          3. Memory Context Build
          4. Decision Engine
          5. Route → LLM / Tool / Hybrid / Plan
          6. Tool Calls Execution (via Sandbox)
          7. Memory Update
          8. Return Response
        """
        self._total_requests += 1

        # ── Step 1: فلترة المدخل ────────────────────────────
        clean_input, err = self._sandbox.validator.validate_user_input(user_input)
        if err and not clean_input:
            return f"🛡️ {err}"

        # ── Step 2: Intent Detection ─────────────────────────
        intent, confidence, _ = self._detector.detect(clean_input)

        # ── Step 3: Memory → Context ─────────────────────────
        self._ctx.add_user(clean_input)
        messages = self._ctx.build(clean_input)

        # ── Step 4: Decision Engine ──────────────────────────
        decision = self._decision.decide(intent, clean_input, messages)

        # ── Step 5: Route ────────────────────────────────────
        if decision.mode == "plan" or self._planner.should_plan(clean_input):
            response = self._handle_plan(clean_input, messages)
        else:
            result   = self._router.route(intent, clean_input, messages)
            response = self._process_route_result(result)

        # ── Step 6: Memory Update ────────────────────────────
        self._ctx.add_assistant(response)

        # Hook
        if self.on_llm_response:
            self.on_llm_response(response)

        return response

    # ══════════════════════════════════════════════════════════
    #  معالجة نتيجة الـ Route
    # ══════════════════════════════════════════════════════════

    def _process_route_result(self, result: RouteResult) -> str:
        """
        يعالج نتيجة TaskRouter:
          • لو فيه tool_calls → ينفّذها عبر Sandbox
          • لو مفيش → يرجع الـ content مباشرة
        """
        if not result.success:
            return f"❌ خطأ: {result.error}"

        final_parts = []

        # ── نص LLM ──────────────────────────────────────────
        if result.content:
            final_parts.append(result.content)

        # ── Tool Calls من LLM ────────────────────────────────
        if result.tool_calls:
            tool_results = self._execute_tool_calls(result.tool_calls)
            if tool_results:
                # نرسل النتائج للـ LLM ليفسّرها
                followup = self._followup_with_results(tool_results)
                if followup:
                    final_parts.append(followup)

        return "\n\n".join(final_parts) if final_parts else "✅ تم التنفيذ"

    def _execute_tool_calls(self, tool_calls: list) -> List[Dict]:
        """
        تنفيذ tool calls من LLM عبر Sandbox.
        كل call يمر على Security Layer كاملة.
        """
        results = []
        for tc in tool_calls:
            # دعم Groq و Ollama format
            if isinstance(tc, dict):
                name = tc.get("function", {}).get("name") or tc.get("name", "")
                args = tc.get("function", {}).get("arguments") or tc.get("arguments", {})
            else:
                continue

            # Parse args لو كانت string
            if isinstance(args, str):
                import json
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            if not name:
                continue

            # تنفيذ عبر Sandbox
            result = self._sandbox.run(name, args)

            # تحديث الذاكرة بنتيجة الـ tool
            self._ctx.add_tool_result(name, result)

            results.append({
                "tool":   name,
                "args":   args,
                "result": result,
            })

        return results

    def _followup_with_results(self, tool_results: List[Dict]) -> str:
        """
        بعد تنفيذ الـ tools، نبعت النتائج للـ LLM
        عشان يلخّصها ويرد على المستخدم بشكل طبيعي.
        """
        # بناء رسالة tool results
        tool_msgs = []
        for tr in tool_results:
            tool_msgs.append({
                "role": "tool",
                "content": tr["result"],
                "tool_call_id": tr["tool"],
            })

        # بناء context مع نتائج الأدوات
        messages = self._ctx.build("")
        messages.extend(tool_msgs)
        messages.append({
            "role": "user",
            "content": "لخّص نتائج العمليات السابقة بشكل مفيد للمستخدم."
        })

        try:
            resp = self._llm_chat(messages)
            return resp.get("content", "") if isinstance(resp, dict) else ""
        except Exception:
            # لو فشل الـ followup — ارجع نتائج الـ tools مباشرة
            parts = []
            for tr in tool_results:
                parts.append(f"**{tr['tool']}**: {tr['result'][:300]}")
            return "\n".join(parts)

    # ══════════════════════════════════════════════════════════
    #  Multi-Step Planning
    # ══════════════════════════════════════════════════════════

    def _handle_plan(self, text: str, messages: list) -> str:
        """ينفّذ خطة متعددة الخطوات"""
        self._plans_created += 1
        plan = self._planner.create_plan(text)

        if not plan.steps:
            # fallback: عالج كطلب عادي
            result = self._router.route(Intent.CHAT, text, messages)
            return self._process_route_result(result)

        # اطبع ملخص الخطة
        plan_summary = plan.summary()
        self._logger.log_info(f"Plan created: {len(plan.steps)} steps")

        # تنفيذ الخطوات
        step_results = self._planner.execute_plan(plan, messages)

        # بناء الرد النهائي
        response_parts = [f"📋 **خطة التنفيذ:**\n{plan_summary}\n"]
        for i, (step, result) in enumerate(zip(plan.steps, step_results), 1):
            status = "✅" if step.status == "done" else "❌"
            response_parts.append(f"{status} **{i}. {step.description}**\n{result[:500]}")

        return "\n\n".join(response_parts)

    # ══════════════════════════════════════════════════════════
    #  LLM Helper
    # ══════════════════════════════════════════════════════════

    def _llm_chat(self, messages: list) -> dict:
        """wrapper للـ LLM مع error handling"""
        try:
            return self._llm.chat(messages)
        except Exception as e:
            return {"error": str(e), "content": "", "tool_calls": []}

    def _summarize_fn(self, text: str) -> str:
        """يلخّص المحادثة القديمة عبر LLM"""
        try:
            resp = self._llm_chat([
                {"role": "system", "content": "لخّص المحادثة التالية في 3-5 جمل مركّزة على أهم النقاط:"},
                {"role": "user",   "content": text},
            ])
            return resp.get("content", "")
        except Exception:
            return ""

    # ══════════════════════════════════════════════════════════
    #  Hooks
    # ══════════════════════════════════════════════════════════

    def _confirm_tool(self, tool: str, risk: RiskLevel, reason: str) -> bool:
        """يستدعي hook التأكيد من الـ UI"""
        if self.on_tool_confirm:
            return self.on_tool_confirm(tool, risk, reason)
        return True  # افتراضي: وافق

    def _on_step_complete(self, step):
        """يستدعي hook إتمام الخطوة"""
        if self.on_step_done:
            self.on_step_done(step)

    # ══════════════════════════════════════════════════════════
    #  Public APIs للتحكم
    # ══════════════════════════════════════════════════════════

    def remember(self, key: str, value: str):
        """يحفظ معلومة في الذاكرة الطويلة"""
        self._ltm.store(key, value, category="user")
        return f"✅ تم حفظ: {key} = {value}"

    def recall(self, key: str) -> str:
        """يسترجع معلومة من الذاكرة الطويلة"""
        val = self._ltm.recall(key)
        return str(val) if val is not None else f"❌ لا يوجد: {key}"

    def add_knowledge(self, text: str, tags: List[str] = None):
        """يضيف معرفة للـ Vector Memory"""
        chunk_id = self._vm.add(text, tags=tags, source="user")
        return f"✅ تمت الإضافة للذاكرة (id: {chunk_id})"

    def search_memory(self, query: str, top_k: int = 3) -> str:
        """يبحث في الـ Vector Memory"""
        return self._vm.search_text(query, top_k=top_k)

    def clear_session(self):
        """يمسح المحادثة الحالية (بدون الذاكرة الطويلة)"""
        self._ctx.clear_session()
        return "✅ تم مسح جلسة المحادثة"

    def set_provider(self, provider: str, **kwargs):
        """تغيير LLM Provider"""
        self._llm.set_provider(provider, **kwargs)

    def grant_permission(self, permission_name: str):
        """منح صلاحية إضافية"""
        from security.permissions import Permission
        try:
            perm = Permission(permission_name)
            self._perms.grant(perm)
            return f"✅ Granted: {permission_name}"
        except ValueError:
            return f"❌ Unknown permission: {permission_name}"

    def revoke_permission(self, permission_name: str):
        """سحب صلاحية"""
        from security.permissions import Permission
        try:
            perm = Permission(permission_name)
            self._perms.revoke(perm)
            return f"✅ Revoked: {permission_name}"
        except ValueError:
            return f"❌ Unknown permission: {permission_name}"

    def add_router_rule(self, fn: Callable):
        """إضافة قاعدة routing مخصصة"""
        self._decision.register_custom_rule(fn)

    # ══════════════════════════════════════════════════════════
    #  Status & Diagnostics
    # ══════════════════════════════════════════════════════════

    @property
    def status(self) -> dict:
        """حالة النظام الكاملة"""
        return {
            "requests":      self._total_requests,
            "plans_created": self._plans_created,
            "memory":        self._ctx.stats(),
            "security":      self._sandbox.stats,
            "security_log":  self._logger.summary(),
        }

    def diagnostics(self) -> str:
        """تقرير تشخيصي كامل"""
        s = self.status
        mem = s["memory"]
        sec = s["security"]
        log = s["security_log"]
        return (
            f"\n{'═'*50}\n"
            f"  PeacockAgent — Diagnostics\n"
            f"{'─'*50}\n"
            f"  📊 Requests     : {s['requests']}\n"
            f"  📋 Plans        : {s['plans_created']}\n"
            f"{'─'*50}\n"
            f"  💾 Short-term   : {mem['short_term_turns']} turns\n"
            f"  📚 Long-term    : {mem['long_term_keys']} keys\n"
            f"  🔍 Vector mem   : {mem['vector_chunks']} chunks\n"
            f"{'─'*50}\n"
            f"  🔒 Tool calls   : {sec['total']} total\n"
            f"  ✅ Allowed      : {sec['allowed']}\n"
            f"  🚫 Blocked      : {sec['blocked']} ({sec['block_rate']})\n"
            f"  📝 Log events   : {log['total_events']}\n"
            f"{'═'*50}\n"
        )

    # ══════════════════════════════════════════════════════════
    #  System Prompt
    # ══════════════════════════════════════════════════════════

    def _default_system_prompt(self) -> str:
        return """أنت PeacockAgent، مساعد ذكاء اصطناعي متقدم على الكمبيوتر.
قدراتك:
  • التحكم في الكمبيوتر (فتح تطبيقات، نقر، كتابة)
  • إدارة الملفات (قراءة، كتابة، حذف)
  • البحث على الإنترنت
  • إنشاء مستندات (Word, PowerPoint, PDF)
  • توليد وتعديل الصور
  • تنفيذ أوامر Terminal
  • كتابة وتصحيح الكود

أنت تعمل بأمان تام — كل عملية حساسة تطلب موافقة المستخدم.
كن واضحاً ومختصراً في ردودك باللغة العربية."""
