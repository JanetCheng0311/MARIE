import os
import requests
import json
import time
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.environ.get("MINIMAX_API_KEY")
# Base host can be overridden by MINIMAX_API_URL env var. Default to minimaxi.chat
BASE_HOST = os.environ.get("MINIMAX_API_URL", "https://api.minimaxi.chat/v1").rstrip("/")
# Full T2A endpoint
BASE_URL = f"{BASE_HOST}/t2a_v2"

def generate_tts(text, voice_id, output_filename):
    """
    Generate speech synthesis using the T2A v2 API with a cloned voice.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "speech-2.6-hd", # Latest model used in minimax_poll.py
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            # Request Cantonese pronunciation
            "language": "Cantonese",
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 1
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    }
    
    print(f"Generating audio for text: '{text[:50]}...'")
    print(f"Using Voice ID: {voice_id}")
    
    resp = requests.post(BASE_URL, headers=headers, json=payload)
    
    # Check for HTTP errors
    resp.raise_for_status()
    
    # The T2A v2 API returns JSON with audio_data or similar
    res = resp.json()
    
    if res.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(f"TTS Generation failed: {json.dumps(res, indent=2)}")
    
    # The audio is usually in 'data' or 'audio_data' as hex/base64 or direct bytes depending on the endpoint
    # For minimaxi.chat/v1/t2a_v2, it typically returns a JSON with "data" containing the audio hex or similar
    
    if "data" in res:
        # If data is a dict, it might contain the audio string
        data_content = res["data"]
        if isinstance(data_content, dict):
            # Check common keys
            audio_str = data_content.get("audio") or data_content.get("audio_data") or ""
        else:
            audio_str = data_content

        if audio_str:
            try:
                audio_bytes = bytes.fromhex(audio_str)
            except ValueError:
                # Try base64 if hex fails
                import base64
                audio_bytes = base64.b64decode(audio_str)
            
            with open(output_filename, "wb") as f:
                f.write(audio_bytes)
            print(f"Successfully saved audio to {output_filename}")
        else:
            print("Could not find audio string in 'data'. Content:", data_content)
    else:
        print("Unexpected response format. Keys found:", res.keys())
        print(json.dumps(res, indent=2))

def main():
    if not API_KEY:
        print("Error: MINIMAX_API_KEY not found.")
        return

    p = argparse.ArgumentParser(description="Generate TTS using a cloned voice")
    p.add_argument("--voice-id", "-v", default=None, help="Voice ID to use (overrides env)")
    p.add_argument("--text", "-t", default=None, help="Text to synthesize (overrides default) ")
    args = p.parse_args()

    # Collect voice ID candidates from environment.
    # Look for a comma-separated MINIMAX_VOICE_IDS or any env var name containing 'voice' (case-insensitive).
    voice_candidates = []
    env_list = os.environ.get("MINIMAX_VOICE_IDS")
    if env_list:
        for it in env_list.split(","):
            s = it.strip()
            if s and s not in voice_candidates:
                voice_candidates.append(s)

    # Scan all environment variables for keys that mention 'voice' (case-insensitive)
    for k, v in os.environ.items():
        if not v:
            continue
        if "voice" in k.lower() or k.lower().startswith("voiceid") or k.lower().startswith("voice_id"):
            if v not in voice_candidates:
                voice_candidates.append(v)

    # Default fallback
    default_voice = "ClonedVoice20260102142340"

    # If CLI override provided, use it
    if args.voice_id:
        chosen_voice = args.voice_id
    else:
        if not voice_candidates:
            chosen_voice = default_voice
        elif len(voice_candidates) == 1:
            chosen_voice = voice_candidates[0]
        else:
            print("Multiple voice IDs detected in environment:")
            for i, v in enumerate(voice_candidates, start=1):
                print(f"  {i}. {v}")
            # Require explicit selection (no default)
            while True:
                sel = input("Choose voice number (required, 'q' to cancel): ").strip()
                if not sel:
                    print("Selection required. Please enter the number of the voice you want to use.")
                    continue
                if sel.lower() in ("q", "quit", "exit"):
                    print("Selection cancelled by user.")
                    return
                try:
                    idx = int(sel)
                    if 1 <= idx <= len(voice_candidates):
                        chosen_voice = voice_candidates[idx - 1]
                        break
                    else:
                        print(f"Number out of range (1-{len(voice_candidates)}). Try again.")
                except ValueError:
                    print("Invalid input; enter a number or 'q' to cancel.")

    # Text to synthesize (Cantonese example) - allow override
    text = args.text if args.text is not None else "你好，我係你嘅廣東話助手。呢段音頻係用你啱啱複製嘅聲音生成嘅。"
    
    output_dir = "audio_result"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    output_file = os.path.join(output_dir, f"cloned_speech_{int(time.time())}.mp3")
    
    try:
        print(f"Using voice id: {chosen_voice}")
        generate_tts(text, chosen_voice, output_file)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
