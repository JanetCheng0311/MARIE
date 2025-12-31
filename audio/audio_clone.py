"""
Simple audio clone example for Minimax API.

Usage:
  - Set environment variable `MINIMAX_API_KEY` to your API key.
  - Optionally set `MINIMAX_API_URL` to your Minimax endpoint (defaults to placeholder).
  - Run: python audio/audio_clone.py --input path/to/source.wav --voice-id YOUR_VOICE_ID

The script supports endpoints that either return raw audio bytes or JSON with a
base64-encoded `audio_base64` field. It writes output to `cloned_output.wav` by default.
"""

import os
import argparse
import requests
import base64


def load_dotenv_file(path: str) -> None:
    """Load simple KEY=VALUE lines from a .env file into os.environ if not set."""
    if not path:
        return
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and os.environ.get(k) is None:
                    os.environ[k] = v
    except Exception:
        # Don't fail hard on env parsing
        return

DEFAULT_API_URL = "https://api.minimax.io/v1/audio/clone"  # replace with real endpoint
DEFAULT_CREATE_VOICE_URL = "https://api.minimax.io/v1/voices/create"  # replace with real endpoint


def clone_audio(api_key: str, input_path: str, voice_id: str | None, api_url: str) -> bytes:
    """Send input audio to Minimax clone endpoint and return resulting audio bytes.

    This function attempts a multipart/form-data POST with fields:
      - `file`: the input audio file
      - `voice_id`: optional target/cloned voice identifier

    It handles two common response shapes:
      1) Direct audio bytes (Content-Type audio/*)
      2) JSON with `audio_base64` containing base64-encoded audio

    """
    headers = {"Authorization": f"Bearer {api_key}"}

    with open(input_path, "rb") as f:
        files = {"file": (os.path.basename(input_path), f, "application/octet-stream")}
        data = {}
        if voice_id:
            data["voice_id"] = voice_id

        resp = requests.post(api_url, headers=headers, files=files, data=data, timeout=120)

    resp.raise_for_status()

    # If response is audio bytes
    content_type = resp.headers.get("Content-Type", "")
    if content_type.startswith("audio/") or content_type == "application/octet-stream":
        return resp.content

    # Otherwise try JSON with base64
    try:
        j = resp.json()
    except ValueError:
        raise RuntimeError("Unexpected response type and not JSON; headers: %r" % resp.headers)

    if "audio_base64" in j:
        return base64.b64decode(j["audio_base64"])

    # Some APIs return a URL to the file
    if "audio_url" in j:
        audio_resp = requests.get(j["audio_url"], timeout=120)
        audio_resp.raise_for_status()
        return audio_resp.content

    raise RuntimeError("Could not find audio in response JSON: keys=%s" % list(j.keys()))


def create_voice(api_key: str, input_path: str, language: str | None, api_url: str) -> str:
    """Upload an audio sample to create a new voice and return the created voice id.

    The exact fields required vary by provider; this function tries common patterns
    (multipart upload with `file` and `language`/`name` fields) and extracts a
    `voice_id`/`id` from the response JSON.
    """
    headers = {"Authorization": f"Bearer {api_key}"}

    data = {}
    if language:
        data["language"] = language
        data["locale"] = language

    # Support passing a directory containing multiple sample files
    if os.path.isdir(input_path):
        paths = [os.path.join(input_path, fn) for fn in sorted(os.listdir(input_path)) if fn.lower().endswith((".mp3", ".wav"))]
        if not paths:
            raise RuntimeError("No audio files found in directory: %s" % input_path)

        file_objs = []
        files = []
        try:
            for p in paths:
                f = open(p, "rb")
                file_objs.append(f)
                files.append(("file", (os.path.basename(p), f, "application/octet-stream")))

            # include a name hint
            data["name"] = os.path.basename(os.path.normpath(input_path))
            resp = requests.post(api_url, headers=headers, files=files, data=data, timeout=180)
        finally:
            for f in file_objs:
                try:
                    f.close()
                except Exception:
                    pass
    else:
        with open(input_path, "rb") as f:
            files = {"file": (os.path.basename(input_path), f, "application/octet-stream")}
            if language:
                data["language"] = language
                data["locale"] = language
            data["name"] = os.path.splitext(os.path.basename(input_path))[0]

            resp = requests.post(api_url, headers=headers, files=files, data=data, timeout=120)

    resp.raise_for_status()

    try:
        j = resp.json()
    except ValueError:
        raise RuntimeError("Create-voice endpoint did not return JSON; headers: %r" % resp.headers)

    # Common response shapes
    for key in ("voice_id", "id", "voiceId"):
        if key in j:
            return j[key]

    if isinstance(j.get("result"), dict) and "voice_id" in j["result"]:
        return j["result"]["voice_id"]

    if isinstance(j.get("data"), dict):
        for key in ("voice_id", "id"):
            if key in j["data"]:
                return j["data"][key]

    # Try nested search
    def find_id(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("voice_id", "id", "voiceId") and isinstance(v, str):
                    return v
                r = find_id(v)
                if r:
                    return r
        elif isinstance(obj, list):
            for it in obj:
                r = find_id(it)
                if r:
                    return r
        return None

    found = find_id(j)
    if found:
        return found

    raise RuntimeError("Could not determine voice id from create-voice response; keys=%s" % list(j.keys()))


def main():
    # Try loading .env from project root and script parent
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv_file(os.path.join(project_root, ".env"))
    load_dotenv_file(os.path.join(os.getcwd(), ".env"))

    p = argparse.ArgumentParser(description="Clone voice audio via Minimax API (example)")
    p.add_argument("--input", "-i", required=False, default=None, help="Path to source audio file (wav/mp3). If omitted the script will search audio/mp3_files")
    p.add_argument("--voice-id", "-v", default=None, help="Optional target voice id for cloning")
    p.add_argument("--out", "-o", default="cloned_output.wav", help="Output filename")
    p.add_argument("--create-voice", action="store_true", help="Create a new voice from an 'ownvoice' sample and print the generated voice id")
    p.add_argument("--ownvoice", default=None, help="Path to your ownvoice sample (wav/mp3). If omitted, the script looks for audio/mp3_files/ownvoice.* or picks one from audio/mp3_files")
    p.add_argument("--lang", default="yue", help="Language/locale hint for voice creation (default: 'yue' for Cantonese). Use provider codes like zh-HK, yue, etc.")
    p.add_argument("--api-url", default=os.environ.get("MINIMAX_API_URL", DEFAULT_API_URL), help="Minimax API URL")
    p.add_argument("--api-key", default=os.environ.get("MINIMAX_API_KEY"), help="Minimax API key (or set MINIMAX_API_KEY env var)")

    args = p.parse_args()

    if not args.api_key:
        raise SystemExit("Provide API key via --api-key or MINIMAX_API_KEY environment variable")

    # If user requested voice creation from ownvoice sample
    if args.create_voice:
        # determine ownvoice path
        own = args.ownvoice
        if not own:
            default_dir = os.path.join(os.path.dirname(__file__), "mp3_files")
            if os.path.isdir(default_dir):
                files = [os.path.join(default_dir, fn) for fn in sorted(os.listdir(default_dir)) if fn.lower().endswith((".mp3", ".wav"))]
            else:
                files = []

            if not files:
                raise SystemExit("No ownvoice file found in audio/mp3_files; provide --ownvoice PATH")

            if len(files) == 1:
                own = files[0]
                print(f"Using ownvoice sample: {own}")
            else:
                # use the whole directory as the sample set
                own = default_dir
                print(f"Using all {len(files)} samples in directory: {own}")

        voice_id = create_voice(args.api_key, own, args.lang, os.environ.get("MINIMAX_CREATE_VOICE_URL", DEFAULT_CREATE_VOICE_URL))
        print(f"Created voice id: {voice_id}")
        return

    # If input not provided, try to find local mp3 files in audio/mp3_files
    if not args.input:
        default_dir = os.path.join(os.path.dirname(__file__), "mp3_files")
        files = []
        if os.path.isdir(default_dir):
            for fn in sorted(os.listdir(default_dir)):
                if fn.lower().endswith((".mp3", ".wav")):
                    files.append(os.path.join(default_dir, fn))

        if not files:
            raise SystemExit("No local audio files found in audio/mp3_files; provide --input")

        if len(files) == 1:
            chosen = files[0]
            print(f"Using discovered audio file: {chosen}")
        else:
            print("Found multiple audio files in audio/mp3_files:")
            for i, fpath in enumerate(files, start=1):
                print(f"  {i}. {os.path.basename(fpath)}")
            sel = input("Choose file number (Enter=1): ").strip()
            try:
                idx = int(sel) if sel else 1
                chosen = files[idx - 1]
            except Exception:
                raise SystemExit("Invalid selection")

        args.input = chosen

    print(f"Calling Minimax clone API at {args.api_url} with input {args.input}...")

    audio_bytes = clone_audio(args.api_key, args.input, args.voice_id, args.api_url)

    with open(args.out, "wb") as out_f:
        out_f.write(audio_bytes)

    print(f"Wrote cloned audio to {args.out}")


if __name__ == "__main__":
    main()
