#!/usr/bin/env python3
"""
Simple CLI: send one question to the AI at SERVER_IP, get a Cantonese reply,
then create TTS audio via Minimax and save the resulting MP3.
"""
import os
import sys
import time
import json
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

SERVER_IP = os.environ.get("SERVER_IP")
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
VOICE_ID = os.environ.get("VOICEID01") or os.environ.get("VoiceID01") or os.environ.get("VoiceID") or "Cantonese_CuteGirl"

if not SERVER_IP:
    print("Error: SERVER_IP not set in environment or .env")
    sys.exit(1)
if not MINIMAX_API_KEY:
    print("Error: MINIMAX_API_KEY not set in environment or .env")
    sys.exit(1)


def load_system_prompt():
    # Prefer txt_files/marie_system_prompt.txt if present
    alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'txt_files', 'marie_system_prompt.txt')
    if os.path.exists(alt):
        try:
            with open(alt, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return "You are a helpful assistant."
    return "You are a helpful assistant."


def query_server(question, timeout=20):
    system_prompt = load_system_prompt()
    # Ensure reply is in Cantonese (allow mixing English if needed)
    user_content = f"{question}\n\n請用廣東話回答，必要時可混用英語。"

    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "top_p": 0.9,
        "n": 1,
        "stream": False,
        "max_output_tokens": 600
    }
    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(SERVER_IP, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Normalize to common completions schema
        if isinstance(data, dict):
            # Try OpenAI-like structure
            if "choices" in data and isinstance(data["choices"], list):
                choice = data["choices"][0]
                # support both chat and legacy formats
                if isinstance(choice.get("message"), dict):
                    return choice["message"].get("content", "")
                return choice.get("text", "")
            # Try direct field
            if "reply" in data:
                return data["reply"]
        # Fallback to raw text
        return resp.text
    except Exception as e:
        return f"<ERROR querying AI: {e}>"


def create_minimax_tts(text, voice_id=VOICE_ID):
    base = "https://api.minimax.io/v1"
    url = f"{base}/t2a_async_v2"
    payload = {
        "model": "speech-2.6-turbo",
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1,
            "vol": 1,
            "pitch": 1
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    }
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post(url, headers=headers, json=payload)
    try:
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Minimax TTS creation failed: {e} - {resp.text}")

    data = resp.json()
    # Expect task_id in response
    task_id = data.get("task_id") or data.get("taskId")
    if not task_id:
        raise RuntimeError(f"No task_id in Minimax response: {json.dumps(data, ensure_ascii=False)}")
    return int(task_id)


def poll_minimax_task(task_id, max_attempts=240, interval=2):
    base = "https://api.minimax.io/v1"
    query_url = f"{base}/query/t2a_async_query_v2?task_id={task_id}"
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "content-type": "application/json"}

    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        resp = requests.get(query_url, headers=headers)
        try:
            data = resp.json()
        except Exception:
            data = {}
        status = data.get("status") or data.get("task_status")
        if status == "Success":
            file_id = data.get("file_id")
            if file_id:
                return file_id
        elif status and status.lower() in ("failed", "error"):
            raise RuntimeError(f"Minimax task failed: {json.dumps(data, ensure_ascii=False)}")
        time.sleep(interval)
    raise RuntimeError("Minimax polling timed out")


def download_file(file_id, out_dir=None):
    base = "https://api.minimax.io/v1"
    url = f"{base}/files/{file_id}"
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "content-type": "application/json"}

    resp = requests.get(url, headers=headers)
    resp.raise_for_status()

    if out_dir is None:
        # Default to the repo's audio/audio_result folder
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(script_dir, "audio_result")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"ai_tts_{ts}.mp3")
    with open(out_path, 'wb') as f:
        f.write(resp.content)
    return out_path


def main():
    # Accept a single question via CLI arg or interactive input
    out_dir = None
    args = sys.argv[1:]
    if "--out-dir" in args:
        i = args.index("--out-dir")
        if i + 1 < len(args):
            out_dir = args[i + 1]
            # remove from question args
            args = args[:i] + args[i + 2 :]

    if args:
        question = " ".join(args)
    else:
        question = input("請輸入你想問嘅問題 (一條): ")

    if not question.strip():
        print("No question provided. Exiting.")
        sys.exit(0)

    print("Querying AI server for Cantonese reply...")
    reply = query_server(question)
    print("AI reply:\n", reply)

    print("Creating Minimax TTS task...")
    try:
        task_id = create_minimax_tts(reply, voice_id=VOICE_ID)
        print(f"Minimax task created: {task_id}. Polling for completion...")
        file_id = poll_minimax_task(task_id)
        print(f"Task completed, file_id: {file_id}. Downloading...")
        path = download_file(file_id, out_dir=out_dir)
        print(f"Saved audio to: {path}")
    except Exception as e:
        print("Error during TTS flow:", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
