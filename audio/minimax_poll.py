"""
This example demonstrates how to create a speech synthesis task, query its status, and download the result.
Note: Make sure to set your API key in the environment variable MINIMAX_API_KEY.
"""
import requests
import json
import os
import time
import dotenv
from datetime import datetime
dotenv.load_dotenv()

api_key = os.environ.get("MINIMAX_API_KEY")
if not api_key:
    print("Error: MINIMAX_API_KEY environment variable is not set")
    exit(1)

import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--task-id', type=int, help='Existing task ID to poll and download')
args = parser.parse_args()

if args.task_id:
    task_id = args.task_id
    print(f"Using provided task_id: {task_id}")
    # Skip creation, go to polling
else:
    # Step 1: Create TTS job
    url = "https://api.minimax.io/v1/t2a_async_v2"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Load input from JSON file in ../json_files/text_file.json
    json_file_path = os.path.join(script_dir, "text_file.json")

    with open(json_file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    # `text` field contains the text to send to the TTS API
    text = data.get("text", "")

    payload = json.dumps({
        "model": "speech-2.6-turbo",
        "text": text,
        "voice_setting": {
            "voice_id": "Cantonese_CuteGirl",
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
    })
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    print("POST response status:", response.status_code)
    post_response_json = None
    try:
        post_response_json = response.json()
        print("POST response JSON:", json.dumps(post_response_json, ensure_ascii=False, indent=2))
    except Exception:
        print("POST response text:", response.text)

    # If server returned an HTTP error, show payload and headers for debugging
    if response.status_code >= 400:
        print("Error: HTTP status", response.status_code)
        try:
            parsed_payload = json.loads(payload)
            print("Request payload:", json.dumps(parsed_payload, ensure_ascii=False, indent=2))
        except Exception:
            print("Request payload (raw):", payload)
        print("Response headers:", dict(response.headers))
        exit(1)

    # keep reference to the response data for later debugging
    response_data = post_response_json if isinstance(post_response_json, dict) else {}

    # Check for API errors
    if "base_resp" in response_data:
        base_resp = response_data.get("base_resp", {})
        if base_resp.get("status_code") != 0:
            print(f"API Error: {base_resp.get('status_msg')}")
            exit(1)

    task_id = response_data.get("task_id")
    if not task_id:
        print("Error: No task_id in response")
        exit(1)
    print(f"Created TTS job with task_id: {task_id}")
url = f"https://api.minimax.io/v1/query/t2a_async_query_v2?task_id={task_id}"

payload = {}
headers = {
    'Authorization': f'Bearer {api_key}',
    'content-type': 'application/json',
}

max_attempts = 240
attempt = 0
while True:
    attempt += 1
    response = requests.request("GET", url, headers=headers, data=payload)
    print(f"Poll HTTP status: {response.status_code}")
    try:
        response_data = response.json()
        print("Poll response JSON:", json.dumps(response_data, ensure_ascii=False))
    except Exception:
        print(f"Error: Failed to parse JSON response: {response.text}")
        response_data = {}

    status = response_data.get("status") or response_data.get("task_status")
    if status == "Success":
        file_id = response_data.get("file_id")
        if file_id:
            break
        else:
            print("Warning: Status is Success but file_id is missing, continuing to poll...")
    elif status in ("failed", "error", "Failed"):
        print(f"Task failed with status: {status}")
        print("Failed poll response:")
        try:
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
        except Exception:
            print(response.text)
        # Also print original POST response for correlation if available
        if post_response_json:
            print("Original POST response:")
            try:
                print(json.dumps(post_response_json, indent=2, ensure_ascii=False))
            except Exception:
                print(post_response_json)
        # Print request payload for debugging (no auth headers shown here)
        try:
            print("Request payload:", json.dumps(json.loads(payload), indent=2, ensure_ascii=False))
        except Exception:
            print("Request payload (raw):", payload)
        # Print response headers from last poll
        try:
            print("Poll response headers:", dict(response.headers))
        except Exception:
            pass
        exit(1)

    if attempt >= max_attempts:
        print(f"Error: Polling timed out after {max_attempts} attempts.")
        exit(1)

    time.sleep(2)  # Wait before polling again

# Step 3: Download and save the file
url = f"https://api.minimax.io/v1/files/{file_id}"

payload = {}
headers = {
    'content-type': 'application/json',
    'Authorization': f'Bearer {api_key}'
}

response = requests.request("GET", url, headers=headers, data=payload)

output_dir = os.path.join(os.path.dirname(script_dir), "audio_result")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "generated_audio.mp3")

with open(output_path, 'wb') as f:
    f.write(response.content)

print(f"File saved as {output_path}")