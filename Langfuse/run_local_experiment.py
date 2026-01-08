#!/usr/bin/env python3
"""Run a simple local experiment and record traces + scores to Langfuse.

This follows the Langfuse docs pattern: for local data we create traces for
each item, attach outputs, and add scores via the SDK.

Usage:
  python Langfuse/run_local_experiment.py --name "My Experiment"

Requirements: set LANGFUSE_BASE_URL and LANGFUSE_SECRET_KEY (or other auth)
in .env so `get_client()` can initialize the client.
"""
from __future__ import annotations
import argparse
import dotenv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

dotenv.load_dotenv()

try:
    from langfuse import get_client, Evaluation
except Exception:
    # Some SDK versions may not export Evaluation directly; provide a tiny
    # fallback shim that mirrors the expected structure when creating scores.
    def Evaluation(name: str, value: Any, comment: str | None = None):
        return {"name": name, "value": value, "comment": comment}
    from langfuse import get_client


def sample_task(item: dict) -> str:
    """A trivial task: return a deterministic answer based on input text.

    Replace this with a real model call, e.g., lmstudio/OpenAI client calls.
    """
    q = str(item.get("input", "")).lower()
    if "capital of france" in q or "france" in q:
        return "Paris"
    if "capital of germany" in q or "germany" in q:
        return "Berlin"
    return "I don't know"


def accuracy_evaluator(*, input: str, output: str, expected_output: str, **kwargs):
    if expected_output and expected_output.lower() in (output or "").lower():
        try:
            return Evaluation(name="accuracy", value=1.0, comment="Correct answer found")
        except Exception:
            return {"name": "accuracy", "value": 1.0, "comment": "Correct answer found"}
    try:
        return Evaluation(name="accuracy", value=0.0, comment="Incorrect answer")
    except Exception:
        return {"name": "accuracy", "value": 0.0, "comment": "Incorrect answer"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', '-n', default='Local Experiment', help='Experiment/run name')
    p.add_argument('--data', '-d', default=None, help='Optional JSON file with local data (list of {input, expected_output})')
    args = p.parse_args()

    # Prepare dataset (either from file or tiny built-in sample)
    if args.data:
        data_path = Path(args.data)
        if not data_path.exists():
            raise SystemExit(f"Data file not found: {data_path}")
        data = json.loads(data_path.read_text(encoding='utf-8'))
    else:
        data = [
            {"input": "What is the capital of France?", "expected_output": "Paris"},
            {"input": "What is the capital of Germany?", "expected_output": "Berlin"},
            {"input": "What is the capital of Spain?", "expected_output": "Madrid"},
        ]

    # Init Langfuse client
    try:
        lf = get_client()
    except Exception as e:
        raise SystemExit(f"Failed to init Langfuse client: {e}")

    results = {"run_name": args.name, "started_at": datetime.utcnow().isoformat(), "items": []}

    # For local data, create a trace/observation per item and attach scores
    for idx, item in enumerate(data, start=1):
        inp = item.get('input', '')
        expected = item.get('expected_output', '')
        # Start an observation/span for this item. Use generation type for LLM runs.
        try:
            span = lf.start_observation(name=f"{args.name}-item-{idx}", as_type="generation", input=inp, metadata={"run": args.name})
        except Exception:
            # Fallback to basic span start
            span = lf.start_observation(name=f"{args.name}-item-{idx}")

        # Execute task (replace with model call)
        output = sample_task(item)

        # Update span with output (if span available)
        if span is not None:
            try:
                span.update(output=output)
            except Exception:
                try:
                    span.update(input=inp, output=output)
                except Exception:
                    pass

        # Evaluate and post scores
        eval_res = accuracy_evaluator(input=inp, output=output, expected_output=expected)
        # Normalize eval_res to a JSON-serializable dict
        if isinstance(eval_res, dict):
            eval_dict = eval_res
        else:
            try:
                eval_dict = {"name": getattr(eval_res, 'name', None), "value": getattr(eval_res, 'value', None), "comment": getattr(eval_res, 'comment', None)}
            except Exception:
                eval_dict = {"repr": repr(eval_res)}

        # Use create_score to attach item-level score (best-effort)
        score_error = None
        try:
            lf.create_score(
                name=eval_dict.get('name') or 'evaluation',
                value=eval_dict.get('value'),
                data_type='NUMERIC',
                observation_id=(getattr(span, 'id', None) if span is not None else None),
                comment=eval_dict.get('comment'),
            )
        except Exception as e:
            score_error = str(e)

        # End span
        try:
            span.end()
        except Exception:
            pass

        item_record = {"input": inp, "expected": expected, "output": output, "evaluation": eval_dict}
        if score_error:
            item_record['score_error'] = score_error
        results['items'].append(item_record)

    # Flush client to ensure data sent
    try:
        lf.flush()
    except Exception:
        pass

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(__file__).parent.parent / 'results'
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f'local_experiment_{ts}.json'
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Wrote local experiment results to', out_path)


if __name__ == '__main__':
    main()
