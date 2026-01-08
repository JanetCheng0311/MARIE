"""Simple tester: call a Gradio `/transcribe` API and optionally log to Langfuse.

Usage:
  python langfuse_test.py --url https://work.manakin-gecko.ts.net:8443/ \
	--audio /path/to/file.mp3

Requires:
  pip install gradio_client python-dotenv langfuse
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from gradio_client import Client, handle_file

try:
	# Prefer the helper used in this repo if available
	from langfuse import get_client as get_langfuse_client
except Exception:
	get_langfuse_client = None

try:
	from dotenv import load_dotenv
	load_dotenv()
except Exception:
	pass


def transcribe_once(gradio_url: str, audio_path: str, api_name: str = "/transcribe") -> Any:
	client = Client(gradio_url)
	start = time.time()
	result = client.predict(audio=handle_file(audio_path), api_name=api_name)
	latency = time.time() - start
	return {"result": result, "latency": latency}


def log_to_langfuse(input_desc: str, output: Any, model_name: str = "gradio-transcribe") -> None:
	if get_langfuse_client is None:
		print("Langfuse client not available; skipping Langfuse logging.")
		return

	try:
		lf = get_langfuse_client()
		# Try a generation-style observation; fall back to a simple span if needed
		try:
			span = lf.start_observation(
				name="transcribe-call",
				as_type="generation",
				input=input_desc,
				output=json.dumps(output, ensure_ascii=False),
				model=model_name,
			)
		except Exception:
			span = lf.start_observation(name="transcribe-call", input=input_desc, output=str(output))

		span.end()
		print("Logged to Langfuse")
	except Exception as e:
		print(f"Langfuse logging failed: {e}")


def main() -> None:
	p = argparse.ArgumentParser()
	p.add_argument("--url", required=True, help="Gradio host root, e.g. https://host:8443/")
	p.add_argument("--audio", required=True, help="Local or remote audio file path (HTTP URL or local path)")
	p.add_argument("--api-name", default="/transcribe", help="API name in the Gradio app")
	p.add_argument("--no-langfuse", action="store_true", help="Disable Langfuse logging")
	p.add_argument("--out", help="Optional path to write JSON result")
	args = p.parse_args()

	# Normalize url: gradio_client wants base URL without trailing path
	gradio_url = args.url
	if not gradio_url.endswith("/"):
		gradio_url += "/"

	print(f"Calling {gradio_url} api {args.api_name} with audio {args.audio}")
	try:
		res = transcribe_once(gradio_url, args.audio, api_name=args.api_name)
	except Exception as e:
		print(f"Transcription request failed: {e}")
		return

	print("Transcription result:")
	try:
		print(json.dumps(res["result"], ensure_ascii=False, indent=2))
	except Exception:
		print(res["result"])

	print(f"Latency: {res['latency']:.2f}s")

	if args.out:
		try:
			with open(args.out, "w", encoding="utf-8") as f:
				json.dump(res, f, ensure_ascii=False, indent=2)
			print(f"Wrote result to {args.out}")
		except Exception as e:
			print(f"Failed to write result: {e}")

	if not args.no_langfuse:
		# Describe the input for Langfuse (audio file path + optional size)
		input_desc = args.audio
		try:
			if os.path.exists(args.audio):
				size = os.path.getsize(args.audio)
				input_desc = f"local:{args.audio} (bytes={size})"
		except Exception:
			pass

		log_to_langfuse(input_desc=input_desc, output=res["result"], model_name="gradio-transcribe")


if __name__ == "__main__":
	main()

