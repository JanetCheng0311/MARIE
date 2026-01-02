import os
import requests
import json
import time
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.environ.get("MINIMAX_API_KEY")
# Base URL can be overridden by MINIMAX_API_URL environment variable
# Recommended default: https://api.minimaxi.chat/v1
BASE_URL = os.environ.get("MINIMAX_API_URL", "https://api.minimaxi.chat/v1").rstrip("/")

def concatenate_audio(file_paths, output_path):
    """
    Concatenate multiple audio files into one using ffmpeg.
    """
    if not file_paths:
        return None
    if len(file_paths) == 1:
        return file_paths[0]
    
    print(f"Concatenating {len(file_paths)} files into {output_path}...")
    
    # Create a temporary file list for ffmpeg
    list_file = "files_to_join.txt"
    with open(list_file, "w") as f:
        for p in file_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    
    try:
        # Try to concatenate by copying streams (fast, but requires same format)
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", list_file, "-c", "copy", output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except subprocess.CalledProcessError:
        # If copy fails (e.g. different formats), re-encode
        try:
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
                "-i", list_file, output_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg concatenation failed: {e.stderr.decode()}")
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)


def get_duration_seconds(path: str) -> float:
    """Return duration of an audio file in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        out = proc.stdout.strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0

def upload_file(file_path):
    """
    Step 1: Upload an audio file to retrieve a file_id.
    The file should be 10s - 5mins, under 20MB.
    """
    url = f"{BASE_URL}/files/upload"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    # purpose must be 'voice_clone' for this flow
    data = {"purpose": "voice_clone"}
    
    print(f"Uploading file: {file_path}...")
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        resp = requests.post(url, headers=headers, data=data, files=files)
    
    resp.raise_for_status()
    res = resp.json()
    
    if res.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(f"Upload failed: {json.dumps(res, indent=2)}")
    
    file_id = res["file"]["file_id"]
    return file_id

def clone_voice(file_id, voice_id):
    """
    Step 2: Call the Voice Clone API with the file_id and a custom voice_id.
    voice_id must be at least 8 chars, start with a letter, and contain letters/numbers.
    """
    url = f"{BASE_URL}/voice_clone"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    # Allow configuring clone options via environment variables
    clone_model = os.environ.get("MINIMAX_CLONE_MODEL", "speech-2.6-hd")
    noise_reduction = os.environ.get("MINIMAX_CLONE_NOISE_REDUCTION", "true").lower() in ("1", "true", "yes")
    need_volume_normalization = os.environ.get("MINIMAX_CLONE_NORMALIZE", "true").lower() in ("1", "true", "yes")
    preview_text = os.environ.get("MINIMAX_CLONE_PREVIEW_TEXT", "測試語音輸出")

    payload = {
        "file_id": file_id,
        "voice_id": voice_id,
        "model": clone_model,
        "noise_reduction": noise_reduction,
        "need_volume_normalization": need_volume_normalization,
        # Optional short text to generate a demo/preview of the cloned voice
        "text": preview_text
    }
    
    print(f"Cloning voice with file_id {file_id} into voice_id '{voice_id}'...")
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    res = resp.json()
    
    if res.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(f"Clone failed: {json.dumps(res, indent=2)}")
    
    return res

def main():
    if not API_KEY:
        print("Error: MINIMAX_API_KEY not found in environment or .env file.")
        return

    # Directory containing sample audio files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mp3_dir = os.path.join(script_dir, "mp3_files")
    
    # Get all mp3/wav files in the directory
    all_files = [
        os.path.join(mp3_dir, f) for f in sorted(os.listdir(mp3_dir))
        if f.lower().endswith((".mp3", ".wav"))
    ]

    if not all_files:
        print(f"Error: No sample files found in {mp3_dir}")
        return

    # Allow CLI/configurable max duration (seconds). Default to 300s (5 minutes).
    MAX_SECONDS = int(os.environ.get("MAX_VOICE_SAMPLE_SECONDS", "300"))
    print(f"Selecting samples up to total duration {MAX_SECONDS}s")

    # Measure durations and choose as many files as possible (greedy by shortest first)
    files_with_dur = []
    for p in all_files:
        dur = get_duration_seconds(p)
        files_with_dur.append((p, dur))

    # Sort by duration ascending to pack more samples
    files_with_dur.sort(key=lambda x: x[1])

    # Respect both duration and a maximum count of files to include
    MAX_COUNT = int(os.environ.get("MAX_VOICE_SAMPLE_COUNT", "7"))
    selected = []
    total = 0.0
    for p, dur in files_with_dur:
        if len(selected) >= MAX_COUNT:
            break
        if total + dur <= MAX_SECONDS:
            selected.append(p)
            total += dur

    # If nothing selected (single huge file), pick the shortest file
    if not selected:
        files_with_dur.sort(key=lambda x: x[1])
        selected = [files_with_dur[0][0]]
        total = files_with_dur[0][1]

    sample_files = selected
    print(f"Using {len(sample_files)} sample files (total ~{int(total)}s):")
    for i, f in enumerate(sample_files, 1):
        print(f"  {i}. {os.path.basename(f)} ({int(get_duration_seconds(f))}s)")

    try:
        # 1. Concatenate if multiple files
        if len(sample_files) > 1:
            merged_path = os.path.join(script_dir, "merged_samples.mp3")
            sample_path = concatenate_audio(sample_files, merged_path)
        else:
            sample_path = sample_files[0]
            
        # 2. Upload
        file_id = upload_file(sample_path)
        print(f"Successfully uploaded. File ID: {file_id}")
        
        # 3. Clone
        # Generate a unique voice ID
        timestamp = time.strftime("%Y%m%d%H%M%S")
        new_voice_id = f"ClonedVoice{timestamp}"
        
        result = clone_voice(file_id, new_voice_id)
        print("\nSuccess! Voice cloned.")
        print(f"New Voice ID: {new_voice_id}")
        print(f"Response: {json.dumps(result, indent=2)}")
        
        print(f"\nNext Step: Use '{new_voice_id}' as the voice_id in your TTS (T2A) requests.")
        
        # Cleanup merged file if created
        if len(sample_files) > 1 and os.path.exists(sample_path):
            os.remove(sample_path)
            print("Cleaned up merged temporary file.")
        
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    main()
