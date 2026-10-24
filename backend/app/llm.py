"""Single LLM entry point: Gemini first, Groq fallback, paced, cached, mockable.

Never prints or logs API keys. All live calls go through `extract`.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import deque
from datetime import date, datetime
from typing import Callable, Optional

from pydantic import BaseModel, ValidationError

from . import config

PROMPT_VERSION = "v1"
MAX_OUT_TOKENS_DEFAULT = 4096


class LLMUnavailable(Exception):
    """No provider could serve the request (maps to 503 llm_unavailable)."""


class RequestTooLarge(LLMUnavailable):
    """Single request larger than the provider's TPM budget; caller must chunk."""


class RateLimited(Exception):
    def __init__(self, msg: str, retry_after: Optional[float] = None, daily: bool = False):
        super().__init__(msg)
        self.retry_after = retry_after
        self.daily = daily


class Transient(Exception):
    def __init__(self, msg: str, retry_after: Optional[float] = None):
        super().__init__(msg)
        self.retry_after = retry_after


def est_tokens(text: str) -> int:
    return int(len(text) / 3.5) + 1


# --------------------------------------------------------------------------- limiter
class SlidingLimiter:
    """Thread-safe sliding 60s window over requests and estimated tokens."""

    def __init__(self, rpm: int, tpm: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rpm, self.tpm = rpm, tpm
        self.clock, self.sleep = clock, sleep
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def _purge(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= 60.0:
            self._events.popleft()

    def acquire(self, tokens: int) -> float:
        """Block until the call fits both budgets; returns total seconds waited."""
        if tokens > self.tpm:
            raise RequestTooLarge(f"request ~{tokens} tokens exceeds TPM budget {self.tpm}")
        waited = 0.0
        while True:
            with self._lock:
                now = self.clock()
                self._purge(now)
                used = sum(t for _, t in self._events)
                if len(self._events) < self.rpm and used + tokens <= self.tpm:
                    self._events.append((now, tokens))
                    return waited
                # earliest time enough budget frees up
                need_tokens = used + tokens - self.tpm
                wait = 0.0
                if len(self._events) >= self.rpm:
                    idx = len(self._events) - self.rpm
                    wait = max(wait, self._events[idx][0] + 60.0 - now)
                if need_tokens > 0:
                    freed = 0
                    for ts, t in self._events:
                        freed += t
                        if freed >= need_tokens:
                            wait = max(wait, ts + 60.0 - now)
                            break
                wait = max(wait, 0.01)
            self.sleep(wait)
            waited += wait


# --------------------------------------------------------------------------- usage / log
_usage_lock = threading.Lock()


def _usage_path():
    return config.CACHE / "usage.json"


def _read_usage() -> dict:
    p = _usage_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    if d.get("date") != date.today().isoformat():
        d = {"date": date.today().isoformat(), "counts": {}, "exhausted": []}
    return d


def _write_usage(d: dict) -> None:
    _usage_path().write_text(json.dumps(d), encoding="utf-8")


def usage_count(provider: str) -> int:
    with _usage_lock:
        return _read_usage()["counts"].get(provider, 0)


def total_live_calls() -> int:
    with _usage_lock:
        return sum(_read_usage()["counts"].values())


def _bump(provider: str) -> int:
    with _usage_lock:
        d = _read_usage()
        d["counts"][provider] = d["counts"].get(provider, 0) + 1
        _write_usage(d)
        return d["counts"][provider]


def _mark_exhausted(provider: str) -> None:
    with _usage_lock:
        d = _read_usage()
        if provider not in d["exhausted"]:
            d["exhausted"].append(provider)
        _write_usage(d)


def _is_exhausted(provider: str, rpd: int) -> bool:
    with _usage_lock:
        d = _read_usage()
        return provider in d["exhausted"] or d["counts"].get(provider, 0) >= rpd


def _log(provider: str, purpose: str, tokens: int, latency: float, hit: bool) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{provider}\t{purpose}\t{tokens}\t{latency:.2f}s\t{'HIT' if hit else 'MISS'}\n"
    try:
        with open(config.CACHE / "calls.log", "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


# --------------------------------------------------------------------------- providers
_limiters: dict[str, SlidingLimiter] = {}


def _limiter(provider: str) -> SlidingLimiter:
    if provider not in _limiters:
        up = provider.upper()
        defaults = {"gemini": (8, 100000), "groq": (20, 5000)}[provider]
        _limiters[provider] = SlidingLimiter(config.env_int(f"{up}_RPM", defaults[0]),
                                             config.env_int(f"{up}_TPM", defaults[1]))
    return _limiters[provider]


def _rpd(provider: str) -> int:
    return config.env_int(f"{provider.upper()}_RPD", {"gemini": 200, "groq": 800}[provider])


def _parse_delay(text: str) -> Optional[float]:
    m = re.search(r"retry in ([\d.]+)\s*s", text, re.I) or re.search(r'retryDelay\W+([\d.]+)s', text)
    if m:
        return float(m.group(1))
    m = re.search(r"try again in (?:(\d+)m)?\s*([\d.]+)s", text, re.I)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return None


def _classify(exc: Exception) -> Exception:
    """Map SDK exceptions to RateLimited / Transient / the original (fatal)."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    msg = str(exc)
    retry = _parse_delay(msg)
    resp = getattr(exc, "response", None)
    try:
        ra = resp.headers.get("retry-after") if resp is not None else None
        if ra:
            retry = float(ra)
    except Exception:
        pass
    if code == 429 or "RESOURCE_EXHAUSTED" in msg:
        daily = bool(re.search(r"PerDay|per day|daily|tokens per day|requests per day", msg, re.I))
        return RateLimited(msg[:300], retry, daily)
    if isinstance(code, int) and code >= 500:
        return Transient(msg[:300], retry)
    if isinstance(exc, (TimeoutError, ConnectionError)) or "timed out" in msg.lower() or "connection" in msg.lower():
        return Transient(msg[:300], retry)
    return exc


def _call_gemini(system: str, user: str, max_out: int) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.env("GEMINI_API_KEY"))
    kwargs = dict(system_instruction=system, response_mime_type="application/json",
                  max_output_tokens=max_out)
    try:
        cfg = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0), **kwargs)
    except Exception:
        cfg = types.GenerateContentConfig(**kwargs)
    resp = client.models.generate_content(model=config.env("GEMINI_MODEL", "gemini-2.5-flash"),
                                          contents=user, config=cfg)
    return resp.text or ""


def _call_groq(system: str, user: str, max_out: int) -> str:
    from groq import Groq

    client = Groq(api_key=config.env("GROQ_API_KEY"))
    resp = client.chat.completions.create(
        model=config.env("GROQ_MODEL", "openai/gpt-oss-120b"),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"}, max_completion_tokens=max_out)
    return resp.choices[0].message.content or ""


_CALLERS = {"gemini": _call_gemini, "groq": _call_groq}
_sleep = time.sleep  # patched in tests


def _call_with_retries(provider: str, system: str, user: str, max_out: int, purpose: str) -> str:
    """Pace, call, retry (max 4 tries). Raises RateLimited(daily=True) / LLMUnavailable."""
    tokens = est_tokens(system + user) + max_out
    lim = _limiter(provider)
    last: Exception | None = None
    for attempt in range(4):
        waited = lim.acquire(tokens)
        if waited > 1:
            print(f"[llm] {provider} paced: waited {waited:.1f}s ({purpose})")
        t0 = time.monotonic()
        try:
            n = _bump(provider)
            print(f"[llm] LIVE call {provider} #{n} today (total {total_live_calls()}) purpose={purpose}")
            out = _CALLERS[provider](system, user, max_out)
            _log(provider, purpose, tokens, time.monotonic() - t0, False)
            return out
        except Exception as e:  # noqa: BLE001
            c = _classify(e)
            _log(provider, purpose, tokens, time.monotonic() - t0, False)
            if isinstance(c, RateLimited):
                if c.daily:
                    _mark_exhausted(provider)
                    raise c
                last = c
                _sleep(min((c.retry_after or 15.0) + 1.0, 90.0))
            elif isinstance(c, Transient):
                last = c
                _sleep(min(c.retry_after or (2 ** attempt * 2 + 0.5), 60.0))
            else:
                raise LLMUnavailable(f"{provider} error: {str(c)[:200]}") from None
    raise RateLimited(f"{provider} exhausted retries: {last}", daily=False)


# --------------------------------------------------------------------------- mock
_mock_handlers: dict[str, Callable[[str, str], dict]] = {}


def register_mock(purpose: str, fn: Callable[[str, str], dict]) -> None:
    _mock_handlers[purpose] = fn


def _mock(schema: type[BaseModel], system: str, user: str, purpose: str) -> BaseModel:
    if purpose in _mock_handlers:
        data = _mock_handlers[purpose](system, user)
    else:
        base = purpose.split(":")[0]
        for name in (purpose.replace(":", "_"), base):
            p = config.FIXTURES / f"{name}.json"
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                break
        else:
            raise LLMUnavailable(f"no mock fixture for purpose '{purpose}'")
    return schema.model_validate(data)


# --------------------------------------------------------------------------- public
def _cache_key(schema: type[BaseModel], system: str, user: str) -> str:
    return hashlib.sha256("\x1f".join([schema.__name__, PROMPT_VERSION, system, user]).encode("utf-8")).hexdigest()


def _parse_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            return json.loads(t[i:j + 1])
        raise


def extract(schema: type[BaseModel], system: str, user: str, *, can_fallback: bool = True,
            purpose: str = "", max_out: int = MAX_OUT_TOKENS_DEFAULT, prefer_groq: bool = False) -> tuple[BaseModel, str]:
    """Return (validated object, provider_name in gemini|groq|cache|mock).

    prefer_groq: try Groq first for small, latency-sensitive calls (only when fallback is allowed);
    Gemini is then the fallback if Groq is exhausted, too large, or returns invalid JSON."""
    if config.llm_mode() == "mock":
        return _mock(schema, system, user, purpose), "mock"

    key = _cache_key(schema, system, user)
    cpath = config.LLM_CACHE_DIR / f"{key}.json"
    if config.cache_enabled() and cpath.exists():
        try:
            obj = schema.model_validate(json.loads(cpath.read_text(encoding="utf-8")))
            _log("cache", purpose, 0, 0.0, True)
            return obj, "cache"
        except Exception:
            pass

    full_system = (f"{system}\n\nRespond with ONE JSON object only, valid against this JSON schema:\n"
                   f"{json.dumps(schema.model_json_schema())}")
    providers = (["groq", "gemini"] if prefer_groq else ["gemini", "groq"]) if can_fallback else ["gemini"]
    errors: list[str] = []
    for prov in providers:
        if not config.env(f"{prov.upper()}_API_KEY"):
            errors.append(f"{prov}: no key")
            continue
        if _is_exhausted(prov, _rpd(prov)):
            errors.append(f"{prov}: daily limit reached")
            continue
        if est_tokens(full_system + user) + max_out > _limiter(prov).tpm:
            errors.append(f"{prov}: request too large for TPM budget")
            if prov == "gemini" and not can_fallback:
                raise RequestTooLarge("; ".join(errors))
            continue
        try:
            msgs_user = user
            for attempt in range(2):
                raw = _call_with_retries(prov, full_system, msgs_user, max_out, purpose)
                try:
                    obj = schema.model_validate(_parse_json(raw))
                    break
                except (ValidationError, json.JSONDecodeError, ValueError) as ve:
                    if attempt == 1:
                        raise LLMUnavailable(f"{prov} returned invalid JSON twice") from None
                    msgs_user = user + f"\n\nYour previous JSON was invalid: {str(ve)[:600]}\nFix your JSON and answer again."
            if config.cache_enabled():
                cpath.write_text(obj.model_dump_json(), encoding="utf-8")
            return obj, prov
        except (RateLimited, LLMUnavailable) as e:
            errors.append(f"{prov}: {str(e)[:150]}")
            continue
    raise LLMUnavailable("; ".join(errors) or "no provider available")
