"""Simple Langfuse smoke test: start an observation, update it, and end it.
This verifies `langfuse` client can be created using keys in .env.
"""
from __future__ import annotations

import os
import traceback

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def main():
    try:
        from langfuse import get_client
    except Exception as e:
        print("langfuse import failed:", e)
        return 1

    try:
        lf = get_client()
    except Exception as e:
        print("get_client() failed:", e)
        traceback.print_exc()
        return 2

    try:
        span = lf.start_observation(name="smoke-test-observation")
        span.update(input="smoke-test-input", output="smoke-test-output", model="smoke-model")
        span.end()
        print("Langfuse smoke test succeeded: observation created and ended.")
    except Exception as e:
        print("Langfuse operation failed:", e)
        traceback.print_exc()
        return 3

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
