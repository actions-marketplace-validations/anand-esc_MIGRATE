"""
agents/converter_critic/graph.py

Real implementation of Agent Suryansh's Converter + Critic module.

Pipeline:
  1. Gemini 1.5 Flash  — semantic Python 2 -> Python 3 conversion
  2. NVIDIA MiniMax    — critic review: does the conversion look correct?

Both API keys are injected at runtime via environment variables:
  GEMINI_API_KEY  — set as a GitHub Actions repository secret
  NVIDIA_API_KEY  — set as a GitHub Actions repository secret

The function signature matches the contract defined in _stubs.py:
  run(fn: ClassifiedFunction) -> ConversionResult
"""

from __future__ import annotations

import os
import re
import requests

from shared.schemas import ClassifiedFunction, ConversionResult

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")

_FENCE_RE = re.compile(r"```(?:python)?\n?(.*?)```", re.DOTALL)


def _extract_code(text: str) -> str:
    """Pull the first fenced code block out of an LLM response."""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _call_gemini(prompt: str) -> str:
    """Call Gemini 1.5 Flash via REST and return the text response."""
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set.")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_nvidia(prompt: str) -> str:
    """Call NVIDIA MiniMax via REST and return the text response."""
    if not NVIDIA_API_KEY:
        raise EnvironmentError("NVIDIA_API_KEY is not set.")

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
    }
    payload = {
        "model": "minimaxai/minimax-m3",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def run(fn: ClassifiedFunction) -> ConversionResult:
    """
    Convert a Python 2 function to Python 3 using Gemini, then
    critic-review it with NVIDIA MiniMax.

    Returns a ConversionResult whose critic_verdict is one of:
      - "clean"                — NVIDIA approved the conversion
      - "leftover_py2_syntax"  — NVIDIA flagged remaining Py2 issues
      - "signature_mismatch"   — NVIDIA detected a changed call signature
      - "conversion_failed"    — Gemini or NVIDIA API call failed entirely
    """
    # ------------------------------------------------------------------ #
    # Stage 1: Conversion via Gemini                                      #
    # ------------------------------------------------------------------ #
    conversion_prompt = f"""You are an expert Python migration engineer.
Convert the following Python 2 function to idiomatic, correct Python 3.12.

Rules:
- Preserve the exact function name and signature.
- Replace all Python 2 idioms semantically (e.g. filter/map return iterators in Py3 — wrap in list() if the original expected a list).
- Replace unicode -> str, basestring -> (str, bytes), long -> int, xrange -> range.
- Move reduce to functools.reduce.
- Replace file() with open(), sys.maxint with sys.maxsize.
- Replace cPickle with pickle, Queue with queue, ConfigParser with configparser.
- Use integer division // where Py2 / on integers was intended.
- Output ONLY the converted code inside a ```python block. No explanation.

```python
{fn.source_code}
```"""

    try:
        gemini_raw = _call_gemini(conversion_prompt)
        converted_code = _extract_code(gemini_raw)
    except Exception as exc:
        return ConversionResult(
            function_id=fn.function_id,
            converted_code=None,
            critic_verdict="conversion_failed",
            critic_notes=f"Gemini API error: {exc}",
        )

    # ------------------------------------------------------------------ #
    # Stage 2: Critic review via NVIDIA MiniMax                           #
    # ------------------------------------------------------------------ #
    critic_prompt = f"""You are a strict Python 3 code reviewer.

Original Python 2 function:
```python
{fn.source_code}
```

Proposed Python 3 conversion:
```python
{converted_code}
```

Evaluate the conversion. Reply with EXACTLY ONE of these tokens and nothing else:
- CLEAN              — conversion is correct and complete
- LEFTOVER_PY2       — there is still Python 2 syntax or semantics remaining
- SIGNATURE_MISMATCH — the function name or argument list was changed"""

    try:
        critic_raw = _call_nvidia(critic_prompt).strip().upper()
    except Exception as exc:
        # Critic failure: accept the conversion but flag for human review
        return ConversionResult(
            function_id=fn.function_id,
            converted_code=converted_code,
            critic_verdict="leftover_py2_syntax",
            critic_notes=f"NVIDIA critic API error (defaulting to needs_review): {exc}",
        )

    # Map NVIDIA's token to the schema's allowed verdict literals
    if "SIGNATURE_MISMATCH" in critic_raw:
        verdict = "signature_mismatch"
    elif "LEFTOVER_PY2" in critic_raw:
        verdict = "leftover_py2_syntax"
    else:
        # CLEAN or any unrecognised response defaults to approved
        verdict = "clean"

    return ConversionResult(
        function_id=fn.function_id,
        converted_code=converted_code,
        critic_verdict=verdict,
        critic_notes=critic_raw,
    )
