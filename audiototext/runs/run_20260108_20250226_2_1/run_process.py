"""Wrapper to run the general processor for a single MP3 (20250226_2_1.mp3).

Usage:
  python run_process.py [--server-ip SERVER_URL] [--gradio-url GRADIO_URL] [--no-langfuse]

This script finds the target MP3 in the local `audiototext/choppedmp3_2` folder,
computes its index, and invokes the repository-wide processor script with args
targeting only that file.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

TARGET_MP3 = "20250226_2_1(30s).mp3"
TARGET_DIR = "choppedmp3_3"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--server-ip", help="Model server endpoint to use (optional)")
    p.add_argument("--gradio-url", help="Gradio transcription URL (optional)")
    p.add_argument("--no-langfuse", action="store_true", help="Do not call Langfuse")
    args = p.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    base_dir = os.path.join(repo_root, "audiototext", TARGET_DIR)
    process_script = os.path.join(repo_root, "audiototext", "process_cantonese_transcribe_and_correct.py")

    if not os.path.isdir(base_dir):
        print("Expected choppedmp3_2 folder not found:", base_dir)
        sys.exit(1)

    files = sorted([n for n in os.listdir(base_dir) if n.lower().endswith(".mp3")])
    if TARGET_MP3 not in files:
        print(f"{TARGET_MP3} not found in {base_dir}")
        sys.exit(1)

    idx = files.index(TARGET_MP3) + 1  # processor uses 1-based start/end-index

    cmd = [sys.executable, process_script, "--dir", base_dir, "--start-index", str(idx), "--end-index", str(idx)]
    if args.gradio_url:
        cmd.extend(["--gradio-url", args.gradio_url])
    if args.server_ip:
        cmd.extend(["--server-ip", args.server_ip])
    if args.no_langfuse:
        cmd.append("--no-langfuse")

    print("Running:", " ".join(cmd))
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
