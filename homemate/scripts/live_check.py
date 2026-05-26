"""Minimal live-API sanity check for Anthropic Claude.

Run this once you've put your key in ``.env``::

    python -m homemate.scripts.live_check

It sends ONE small message (a few tokens of input, <= 30 tokens of output) to
verify that the key, network, and selected model all work. Exits 0 on success,
non-zero on any failure with a human-readable reason.

This is intentionally separate from the main agent so you can budget exactly
one tiny API call to verify connectivity before running the full demo.
"""

from __future__ import annotations

import os
import sys

try:
    from dotenv import load_dotenv
    # override=True so an empty inherited ANTHROPIC_API_KEY doesn't shadow .env
    load_dotenv(override=True)
except ImportError:
    pass  # dotenv is optional; env vars set directly still work

from .. import config  # noqa: E402


def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("[FAIL] ANTHROPIC_API_KEY is not set. Edit .env and try again.")
        return 2
    if not key.startswith("sk-"):
        print(f"[warn] ANTHROPIC_API_KEY does not look like a real key "
              f"(prefix: {key[:6]!r}). Continuing anyway.")

    try:
        from anthropic import Anthropic
    except ImportError:
        print("[FAIL] anthropic package not installed. "
              "Run: pip install -r requirements.txt")
        return 3

    model = config.LLM_MODEL
    print(f"[info] Pinging Claude. model={model}")
    try:
        client = Anthropic(api_key=key)
        resp = client.messages.create(
            model=model,
            max_tokens=20,
            messages=[{"role": "user",
                       "content": "Reply with exactly the two characters: OK"}],
        )
    except Exception as e:
        print(f"[FAIL] API call raised {type(e).__name__}: {e}")
        return 4

    text_blocks = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    reply = (text_blocks[0] if text_blocks else "").strip()
    usage = getattr(resp, "usage", None)
    in_tok = getattr(usage, "input_tokens", "?") if usage else "?"
    out_tok = getattr(usage, "output_tokens", "?") if usage else "?"
    print(f"[info] reply={reply!r}  input_tokens={in_tok}  output_tokens={out_tok}")

    if "OK" in reply.upper():
        print("[OK] Claude is reachable and responding. Phase 2 is live.")
        return 0
    print("[warn] Reply did not contain 'OK' but the call succeeded. "
          "Connectivity is fine; the model just chose different wording.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
