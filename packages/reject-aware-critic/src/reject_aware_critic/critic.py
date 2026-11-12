"""Single-critic interface — one vendor, one decoding configuration.

`Critic.judge(candidate)` executes one chat-completion round trip and returns
a Verdict. Network / parse errors are surfaced as Verdict(decision='ERROR' or
'PARSE_FAIL') rather than raised — so an ensemble can tolerate partial failure.

Cost guardrail: each call estimates USD cost from the server-reported usage
(falling back to chars/4 heuristic). If cost > `max_cost_usd`, a
`CostBudgetError` is raised AFTER the call (we can't predict cost before).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import _vendors
from .filters import detect_traps_strict, merge_trap_flags
from .prompts import DEFAULT_SYSTEM_PROMPT, SYSTEM_PROMPTS, build_user_prompt
from .schemas import CandidateClass, TrapFlag, Verdict


class CostBudgetError(RuntimeError):
    """Raised when a single judge() call exceeds the configured max_cost_usd."""


def _extract_json(raw: str) -> dict | None:
    """Best-effort JSON extraction (strip fences, find outermost {..}, tolerate trailing commas)."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1]
        if s.endswith("```"):
            s = s[:-3].rstrip()
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j < 0 or j <= i:
        return None
    candidate = s[i : j + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = candidate.replace(",\n}", "\n}").replace(",\n]", "\n]")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def _normalize_trap_flags(raw: object) -> list[TrapFlag]:
    """Coerce raw LLM-provided trap_flags into the typed Literal list."""
    if not isinstance(raw, list):
        return []
    valid = {
        "mechanism_vs_limit_theorem",
        "mathematical_framework_masquerading",
        "surface_similarity_from_heavy_tails",
        "mechanism_dispersion_monolith",
        "other",
    }
    out: list[TrapFlag] = []
    for x in raw:
        s = str(x).strip().lower()
        if s in valid:
            out.append(s)  # type: ignore[arg-type]
    return out


@dataclass
class Critic:
    """One LLM critic = (vendor, model, decoding config, persona).

    Args:
        vendor: 'deepseek' / 'anthropic' / 'kimi' / 'glm' / 'openrouter' /
            'openai' / 'mock'. See `_vendors.VENDORS` for the registry.
        model: vendor model id, e.g. 'deepseek-chat',
            'anthropic/claude-3-5-sonnet', 'moonshotai/kimi-k2', 'zhipuai/glm-4'.
        critic_id: unique label for this critic in ensemble verdicts.
            Defaults to "{vendor}:{model}:{persona}".
        persona: 'rigorous' (default), 'lighter', 'creative_dissenter'.
        system_prompt: override the persona-derived system prompt.
        temperature: sampling temperature (default 0.0).
        max_tokens: output cap (default 2000).
        api_key: explicit API key (else read from vendor's env var).
        base_url: explicit base URL override.
        max_cost_usd: per-call USD cap (default 0.05). Raises CostBudgetError
            on overage AFTER the call completes.
        cost_per_1k_in / cost_per_1k_out: override per-1k-token pricing.
        log_path: if set, append one JSON line per judge() call here.
        timeout: per-request timeout in seconds.
        http_client: inject an httpx.Client for tests / mocking.
        mock_responder: when vendor='mock', name of the registered responder
            to use (default 'default'). See _vendors.register_mock_responder.

    Example:
        critic = Critic(vendor="deepseek", model="deepseek-chat", temperature=0.0)
        verdict = critic.judge(my_candidate)
        print(verdict.decision, verdict.trap_flags)
    """

    vendor: str = "deepseek"
    model: str = "deepseek-chat"
    critic_id: str = ""
    persona: str = "rigorous"
    system_prompt: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2000
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = field(default=None, repr=False)
    max_cost_usd: float = 0.05
    cost_per_1k_in: float | None = None
    cost_per_1k_out: float | None = None
    log_path: str | None = None
    timeout: float = 180.0
    http_client: Any = field(default=None, repr=False)
    mock_responder: str = "default"

    def __post_init__(self) -> None:
        if self.persona not in SYSTEM_PROMPTS:
            raise ValueError(
                f"Unknown persona '{self.persona}'. "
                f"Known: {sorted(SYSTEM_PROMPTS)}"
            )
        if not self.critic_id:
            self.critic_id = f"{self.vendor}:{self.model}:{self.persona}"
        # validate vendor registry early
        _vendors.get_vendor(self.vendor)

    def _resolved_system_prompt(self) -> str:
        if self.system_prompt is not None:
            return self.system_prompt
        return SYSTEM_PROMPTS.get(self.persona, DEFAULT_SYSTEM_PROMPT)

    def judge(self, candidate: CandidateClass) -> Verdict:
        """Run one critic judgment. Returns a Verdict (never raises on API error)."""
        if not isinstance(candidate, CandidateClass):
            # Permit dict input for ergonomic callers.
            candidate = CandidateClass.model_validate(candidate)

        vendor_cfg = _vendors.get_vendor(self.vendor)
        # mock vendor never needs an API key.
        try:
            api_key = _vendors.resolve_api_key(vendor_cfg, self.api_key)
        except RuntimeError as e:
            return self._error_verdict(candidate.class_id, str(e), elapsed=0.0)

        system_prompt = self._resolved_system_prompt()
        user_prompt = build_user_prompt(candidate)

        t0 = time.time()
        content, usage, err = _vendors.call_chat_completion(
            vendor=vendor_cfg,
            api_key=api_key,
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            base_url_override=self.base_url,
            timeout=self.timeout,
            http_client=self.http_client,
            mock_responder_name=self.mock_responder,
        )
        elapsed = round(time.time() - t0, 3)

        if not usage:
            usage = _vendors.estimate_usage_from_text(system_prompt, user_prompt, content or "")
        cost = _vendors.estimate_cost_usd(
            usage, vendor_cfg, self.cost_per_1k_in, self.cost_per_1k_out
        )

        if err is not None or content is None:
            verdict = self._error_verdict(
                candidate.class_id, err or "no content", elapsed, cost=cost, raw=content
            )
            self._log_call(candidate, verdict, usage, system_prompt, user_prompt)
            self._check_cost_budget(cost, candidate.class_id)
            return verdict

        parsed = _extract_json(content)
        if parsed is None:
            verdict = Verdict(
                class_id=candidate.class_id,
                critic_id=self.critic_id,
                decision="PARSE_FAIL",
                confidence=0.0,
                rationale=content[:300],
                trap_flags=[],
                elapsed_s=elapsed,
                cost_usd=cost,
                raw_response=content,
                error="parse_fail",
            )
            self._log_call(candidate, verdict, usage, system_prompt, user_prompt)
            self._check_cost_budget(cost, candidate.class_id)
            return verdict

        # Build verdict from parsed JSON + detector-augmented trap_flags.
        decision = parsed.get("decision", parsed.get("verdict", "UNCLEAR"))
        confidence = parsed.get("confidence", 0.0)
        rationale = str(parsed.get("rationale", parsed.get("reasoning", "")))[:1000]
        declared = _normalize_trap_flags(parsed.get("trap_flags", []))
        detected = detect_traps_strict(rationale)
        trap_flags = merge_trap_flags(declared, detected)

        verdict = Verdict(
            class_id=candidate.class_id,
            critic_id=self.critic_id,
            decision=decision,
            confidence=confidence,
            rationale=rationale,
            trap_flags=trap_flags,
            elapsed_s=elapsed,
            cost_usd=cost,
            raw_response=content,
            error=None,
        )
        self._log_call(candidate, verdict, usage, system_prompt, user_prompt)
        self._check_cost_budget(cost, candidate.class_id)
        return verdict

    # ------------------------------------------------------------------
    # internals

    def _error_verdict(
        self, class_id: str, msg: str, elapsed: float, cost: float = 0.0, raw: str | None = None
    ) -> Verdict:
        return Verdict(
            class_id=class_id,
            critic_id=self.critic_id,
            decision="ERROR",
            confidence=0.0,
            rationale=msg[:500],
            trap_flags=[],
            elapsed_s=elapsed,
            cost_usd=cost,
            raw_response=raw,
            error=msg[:500],
        )

    def _check_cost_budget(self, cost: float, class_id: str) -> None:
        if cost > self.max_cost_usd:
            raise CostBudgetError(
                f"Critic '{self.critic_id}' on class '{class_id}' cost "
                f"${cost:.4f} > max_cost_usd ${self.max_cost_usd:.4f}. "
                "Raise max_cost_usd or reduce max_tokens / prompt size."
            )

    def _log_call(
        self,
        candidate: CandidateClass,
        verdict: Verdict,
        usage: dict,
        system_prompt: str,
        user_prompt: str,
    ) -> None:
        if not self.log_path:
            return
        record = {
            "ts": time.time(),
            "critic_id": self.critic_id,
            "vendor": self.vendor,
            "model": self.model,
            "persona": self.persona,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "class_id": candidate.class_id,
            "decision": verdict.decision,
            "confidence": verdict.confidence,
            "trap_flags": verdict.trap_flags,
            "elapsed_s": verdict.elapsed_s,
            "cost_usd": round(verdict.cost_usd, 6),
            "usage": usage,
            "error": verdict.error,
            "rationale_excerpt": (verdict.rationale or "")[:200],
            "user_prompt_len": len(user_prompt),
            "system_prompt_len": len(system_prompt),
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # Logging must never break the judge() return path.
            pass
