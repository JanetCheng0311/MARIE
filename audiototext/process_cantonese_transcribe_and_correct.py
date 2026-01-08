"""Transcribe Cantonese audio via a Gradio endpoint, then call multiple AI models
to correct homophone/hanzi mistakes and log timings to Langfuse.

Usage:
  python process_cantonese_transcribe_and_correct.py --dir /path/to/choppedmp3 \
    --gradio-url https://host:8443 --server-ip http://MODEL_HOST:PORT/api/v0/chat/completions
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from typing import Optional

try:
    from gradio_client import Client, handle_file
except Exception:
    Client = None
    handle_file = None

try:
    from langfuse import get_client as get_langfuse_client
except Exception:
    get_langfuse_client = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests


def simplify_repetitions(text: str) -> str:
    """Detect and collapse extreme repetitions (e.g. 'word word word...') 
    common in ASR failures.
    """
    if not text:
        return text
    # Regex to catch phrases or characters repeating 3 or more times
    # This specifically targets long strings of the same character or short phrase.
    # Ref: https://github.com/zai-org/GLM-ASR/issues/26
    # We look for a pattern that repeats at least 4 times
    pattern = re.compile(r"(.+?)\1{3,}")
    
    def sub_func(m):
        # Keep only the first occurrence
        return m.group(1)

    return pattern.sub(sub_func, text)


def transcribe_via_gradio(apath: str, gradio_url: str, api_name: str) -> tuple[str, float]:
    """Call the Gradio /transcribe endpoint and return (text, elapsed_seconds)."""
    if Client is None or handle_file is None:
        raise RuntimeError("gradio_client not installed in environment")
    client = Client(gradio_url)
    start = time.time()
    res = client.predict(audio=handle_file(apath), api_name=api_name)
    elapsed = time.time() - start
    if isinstance(res, dict):
        if "result" in res:
            text = res["result"]
        elif "text" in res:
            text = res["text"]
        else:
            text = str(res)
    else:
        text = str(res)
    return text, elapsed


def call_model_correction(server_url: str, model_name: str, transcript: str, timeout: int = 180) -> tuple[str, float]:
    """Call an LLM server endpoint (SERVER_IP style) to ask the model to correct homophone hanzi errors.
    Returns (reply_text, elapsed_seconds).
    """
    system = (
        "You are an expert Hong Kong Cantonese editor. Your task is to refine Cantonese transcriptions. "
        "Correct all phonetic/homophone errors, improve grammar where it feels unnatural for written Cantonese (Traditional Chinese), "
        "and ensure the flow is professional yet authentic.\n\n"
        "LOGIC & FLUENCY CHECK: "
        "1. Contextual Sanity Check: Ensure names, numbers, and logical arguments in the text make sense. If a word sounds like a common name or entity but is transcribed as a random character, correct it based on the context.\n"
        "2. Natural Flow: Adjust sentence structures to match native Cantonese speech patterns while maintaining the meaning.\n"
        "3. Consistency: Ensure the tone is consistent throughout the script.\n\n"
        "IDENTIFY AND FIX REPETITIONS: ASR models sometimes hallucinate and repeat the same word or phrase many times. "
        "Collapse these repetitions into a single occurrence.\n\n"
        "CRITICAL READABILITY RULE: The input is often a single giant block of text. You MUST break it into logical paragraphs "
        "and separate different speakers or topics with newlines. Each paragraph should be no more than 3-4 sentences."
    )
    user = (
        "Perform a deep logical review and refine the following Cantonese transcription.\n\n"
        "STEPS:\n"
        "1. Fix homophone and character errors (Traditional Chinese).\n"
        "2. Ensure the text is logially coherent and the argument/conversation flows naturally.\n"
        "3. Remove repetitive hallucinations.\n"
        "4. Format with logical paragraph breaks for maximum readability.\n\n"
        "Return ONLY the final refined script. No explanations, no introductory text.\n\n"
        f"TRANSCRIPT:\n{transcript}"
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_output_tokens": 1200,
        "repetition_penalty": 1.1,
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    start = time.time()
    resp = requests.post(server_url, headers=headers, json=payload, timeout=timeout)
    elapsed = time.time() - start
    try:
        resp.raise_for_status()
        j = resp.json()
        # Expecting OpenAI-like response shape
        reply = j.get("choices", [{}])[0].get("message", {}).get("content")
        if reply is None:
            # Fallback: some servers return top-level 'result' or 'output'
            reply = j.get("result") or j.get("output") or json.dumps(j, ensure_ascii=False)
    except Exception as e:
        # Return error string
        reply = f"<ERROR: {e} - {getattr(resp, 'text', '')}>"
    return reply, elapsed


def log_to_langfuse(name: str, input_desc: str, output: str, meta: dict, no_langfuse: bool = False) -> None:
    if get_langfuse_client is None or no_langfuse:
        print("Langfuse logging skipped (no client or --no-langfuse set)")
        return
    try:
        lf = get_langfuse_client()
        span = lf.start_observation(name=name, as_type="generation", input=input_desc, output=output, model=meta.get("model"))
        # attach meta as tags or attributes if supported
        for k, v in meta.items():
            try:
                span.set_attribute(k, v)
            except Exception:
                pass
        span.end()
        print("Logged to Langfuse:", input_desc)
    except Exception as e:
        print("Langfuse logging failed:", e)


def find_mp3_files(base_dir: str) -> list[str]:
    files = []
    for name in sorted(os.listdir(base_dir)):
        if name.lower().endswith(".mp3"):
            files.append(os.path.join(base_dir, name))
    return files


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="choppedmp3", help="Directory with chopped mp3 files")
    p.add_argument("--gradio-url", help="Gradio app base URL for transcription (required)")
    p.add_argument("--api-name", default="/transcribe", help="Gradio API name to call for transcription")
    p.add_argument("--server-ip", help="Model server endpoint (eg http://host:port/api/v0/chat/completions). Uses SERVER_IP env if omitted.")
    p.add_argument("--models-file", default=os.path.join(os.path.dirname(__file__), "..", "json_files", "available_models.json"), help="JSON file listing models to try")
    p.add_argument("--no-langfuse", action="store_true", help="Do not call Langfuse; only print outputs")
    p.add_argument("--start-index", type=int, default=1)
    p.add_argument("--end-index", type=int)
    args = p.parse_args()

    base_dir = args.dir
    if not os.path.isabs(base_dir):
        base_dir = os.path.join(os.getcwd(), base_dir)

    # common fallbacks where choppedmp3 might live
    if not os.path.isdir(base_dir):
        for fallback in (os.path.join(os.getcwd(), "audiototext", "choppedmp3_1"),
                         os.path.join(os.getcwd(), "audiototext", "choppedmp3_2"),
                         os.path.join(os.getcwd(), "podcast_example", "choppedmp3")):
            if os.path.isdir(fallback):
                print(f"Directory {base_dir} not found — using fallback {fallback}")
                base_dir = fallback
                break
    if not os.path.isdir(base_dir):
        print("Directory not found:", base_dir)
        return

    if not args.gradio_url:
        print("--gradio-url is required to call your transcription endpoint")
        return

    server_url = args.server_ip or os.environ.get("SERVER_IP") or os.environ.get("SERVER_API_HOST")
    if not server_url:
        print("Warning: no --server-ip provided and SERVER_IP not set; model correction calls will be skipped")

    # Load models list
    try:
        with open(args.models_file, "r", encoding="utf-8") as fh:
            models = json.load(fh)
    except Exception:
        models = []

    mp3_files = find_mp3_files(base_dir)
    if not mp3_files:
        print("No .mp3 files found in:", base_dir)
        return

    start_idx = max(1, args.start_index)
    end_idx = args.end_index if args.end_index is not None else len(mp3_files)
    slice_files = mp3_files[start_idx - 1 : end_idx]

    # Create a new results directory with datetime
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = os.path.join(os.path.dirname(base_dir), "results", timestamp_str)
    os.makedirs(results_dir, exist_ok=True)
    print(f"Results will be saved to: {results_dir}")

    for apath in slice_files:
        basename = os.path.splitext(os.path.basename(apath))[0]
        print("Processing:", apath)

        # Transcribe
        tpath = os.path.join(results_dir, f"{basename}_{timestamp_str}_raw.txt")
        try:
            transcript_raw, trans_time = transcribe_via_gradio(apath, args.gradio_url, args.api_name)
            transcript = simplify_repetitions(transcript_raw)
            with open(tpath, "w", encoding="utf-8") as f:
                f.write(transcript)
            if transcript != transcript_raw:
                print(f"Transcribed in {trans_time:.2f}s (Cleaned repetitive hallucinations) — saved to {tpath}")
            else:
                print(f"Transcribed in {trans_time:.2f}s — saved to {tpath}")
        except Exception as e:
            print("Transcription failed:", e)
            transcript = ""
            trans_time = 0.0

        # If no server_url or no models or empty transcript, skip correction stage
        if not server_url or not models or not transcript.strip():
            print("Skipping correction stage (missing server_url, models, or empty transcript).")
            continue

        # For each model, call correction and save result
        for model in models:
            try:
                corrected, corr_time = call_model_correction(server_url, model, transcript or "", timeout=180)
            except Exception as e:
                corrected = f"<ERROR: {e}>"
                corr_time = 0.0

            # Save corrected output with requested structure and datetime in filename
            safe_model = model.replace("/", "_")
            out_file = os.path.join(results_dir, f"{basename}.{safe_model}.{timestamp_str}.txt")
            
            file_content = (
                f"--- Result for Model: {model} ---\n"
                f"Audio API Runtime: {trans_time:.2f}s\n"
                f"AI Correction Runtime: {corr_time:.2f}s\n"
                f"Saved to: {out_file}\n"
                f"{'='*40}\n\n"
                f"{corrected}"
            )

            try:
                with open(out_file, "w", encoding="utf-8") as of:
                    of.write(file_content)
            except Exception as e:
                print(f"Failed to save corrected output for {model}: {e}")

        # Correction loop complete for this audio file


if __name__ == "__main__":
    main()
