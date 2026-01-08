"""Send transcript text files to Langfuse without uploading audio.

Usage:
  python send_transcripts_langfuse.py --dir /path/to/choppedmp3

The script looks for a `transcripts/` subfolder (or reads .txt files in the dir),
reads each transcript, and logs an observation to Langfuse that references the
audio file path but does NOT send the audio bytes.
"""
from __future__ import annotations

import argparse
import os
import json
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


def log_to_langfuse(input_desc: str, output: str, model_name: str = "transcript") -> None:
    if get_langfuse_client is None:
        print("Langfuse client not available; skipping Langfuse logging.")
        return

    try:
        lf = get_langfuse_client()
        try:
            span = lf.start_observation(
                name="transcript-log",
                as_type="generation",
                input=input_desc,
                output=output,
                model=model_name,
            )
        except Exception:
            span = lf.start_observation(name="transcript-log", input=input_desc, output=output)

        span.end()
        print("Logged to Langfuse:", input_desc)
    except Exception as e:
        print("Langfuse logging failed:", e)


def find_transcript_files(base_dir: str) -> list[str]:
    transcripts_dir = os.path.join(base_dir, "transcripts")
    files: list[str] = []
    if os.path.isdir(transcripts_dir):
        for name in sorted(os.listdir(transcripts_dir)):
            if name.lower().endswith(".txt"):
                files.append(os.path.join(transcripts_dir, name))
    else:
        for name in sorted(os.listdir(base_dir)):
            if name.lower().endswith(".txt"):
                files.append(os.path.join(base_dir, name))
    return files


def find_mp3_files(base_dir: str) -> list[str]:
    files: list[str] = []
    for name in sorted(os.listdir(base_dir)):
        if name.lower().endswith(".mp3"):
            files.append(os.path.join(base_dir, name))
    return files


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=False, default="choppedmp3", help="Directory containing choppedmp3 (or transcripts subdir)")
    p.add_argument("--no-langfuse", action="store_true", help="Do not call Langfuse; only print what would be sent")
    p.add_argument("--model", default="podcast-transcript", help="Model name to report to Langfuse")
    p.add_argument("--start-index", type=int, default=1, help="1-based index into sorted mp3 list to start processing")
    p.add_argument("--end-index", type=int, help="1-based index into sorted mp3 list to stop (inclusive)")
    p.add_argument("--auto-transcribe", action="store_true", help="Call a Gradio /transcribe endpoint for missing transcripts")
    p.add_argument("--gradio-url", help="Gradio base URL (e.g. https://host:8443/). Required if --auto-transcribe is set")
    p.add_argument("--api-name", default="/transcribe", help="API name in Gradio app when transcribing")
    args = p.parse_args()

    base_dir = args.dir
    if not os.path.isabs(base_dir):
        base_dir = os.path.join(os.getcwd(), base_dir)

    # If the requested directory doesn't exist, try common fallbacks inside the repo.
    if not os.path.isdir(base_dir):
        fallback = os.path.join(os.getcwd(), "podcast_example", "choppedmp3")
        if os.path.isdir(fallback):
            print(f"Directory {base_dir} not found — using fallback {fallback}")
            base_dir = fallback
        else:
            print("Directory not found:", base_dir)
            return

    # Prefer processing all mp3 files; use transcripts when available.
    mp3_files = find_mp3_files(base_dir)
    if not mp3_files:
        print("No .mp3 files found in:", base_dir)
        return

    transcripts_dir = os.path.join(base_dir, "transcripts")

    # Apply optional slice by index (1-based)
    start_idx = max(1, args.start_index)
    end_idx = args.end_index if args.end_index is not None else len(mp3_files)
    slice_files = mp3_files[start_idx - 1 : end_idx]

    for apath in slice_files:
        basename = os.path.splitext(os.path.basename(apath))[0]

        # Try transcripts: transcripts/<basename>.txt or <base_dir>/<basename>.txt
        tpath_candidates = [
            os.path.join(transcripts_dir, f"{basename}.txt"),
            os.path.join(base_dir, f"{basename}.txt"),
        ]

        text = ""
        found_tpath: Optional[str] = None
        for tp in tpath_candidates:
            if os.path.exists(tp):
                try:
                    with open(tp, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                        found_tpath = tp
                        break
                except Exception as e:
                    print("Failed to read", tp, e)

        # If missing and auto-transcribe requested, call Gradio transcribe
        if not found_tpath and args.auto_transcribe:
            if not args.gradio_url:
                print("--auto-transcribe requires --gradio-url; skipping", apath)
            elif Client is None or handle_file is None:
                print("gradio_client not available in environment; cannot transcribe", apath)
            else:
                try:
                    client = Client(args.gradio_url if args.gradio_url.endswith("/") else args.gradio_url + "/")
                    print("Transcribing via Gradio:", apath)
                    res = client.predict(audio=handle_file(apath), api_name=args.api_name)
                    # Attempt to extract text result; model apps vary
                    if isinstance(res, dict):
                        # Common shape: {'result': 'text'} or {'text': '...'}
                        if "result" in res:
                            text = res["result"]
                        elif "text" in res:
                            text = res["text"]
                        else:
                            text = str(res)
                    else:
                        text = str(res)
                    # Write transcript file next to audio for future runs
                    try:
                        tdir = os.path.join(base_dir, "transcripts")
                        if not os.path.isdir(tdir):
                            os.makedirs(tdir, exist_ok=True)
                        tfile = os.path.join(tdir, f"{basename}.txt")
                        with open(tfile, "w", encoding="utf-8") as tf:
                            tf.write(text)
                        found_tpath = tfile
                        print("Wrote transcript:", tfile)
                    except Exception as e:
                        print("Failed to write transcript file:", e)
                except Exception as e:
                    print("Gradio transcription failed:", e)

        # For Langfuse, send only the audio filename as the `input` value.
        audio_name = os.path.basename(apath)
        input_desc = audio_name

        # Keep metadata for local logs only
        meta = []
        try:
            size = os.path.getsize(apath)
            meta.append(f"bytes={size}")
        except Exception:
            meta.append("bytes=unknown")
        if found_tpath:
            meta.append(f"transcript_file={found_tpath}")
        else:
            meta.append("transcript_file=missing")
        meta_str = "; ".join(meta)

        if args.no_langfuse or get_langfuse_client is None:
            print("[DRY]", input_desc, "|", meta_str)
            if text:
                print(text[:400].replace("\n", " ") + ("..." if len(text) > 400 else ""))
            else:
                print("[no transcript available]")
            output_text = text if text else "<TRANSCRIPT_MISSING>"
        else:
            # Log transcript text if available; otherwise log a placeholder message
            output_text = text if text else "<TRANSCRIPT_MISSING>"
            log_to_langfuse(input_desc=input_desc, output=output_text, model_name=args.model)

        # Save a copy of the output to the transcripts folder for review (if transcript exists)
        try:
            if output_text and output_text != "<TRANSCRIPT_MISSING>":
                tdir = os.path.join(base_dir, "transcripts")
                os.makedirs(tdir, exist_ok=True)
                out_file = os.path.join(tdir, f"{basename}.txt")
                with open(out_file, "w", encoding="utf-8") as of:
                    of.write(output_text)
                print("Saved transcript copy:", out_file)
        except Exception as e:
            print("Failed to save transcript copy:", e)


if __name__ == "__main__":
    main()
