# Yue-TruthfulQA Testing System
# This script tests the model's ability to answer Cantonese TruthfulQA questions.
# It uses the data from yue_benchmark/Yue-TruthfulQA.json and follows the pattern of marie_test_ai.py.

import requests
import os
import datetime
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# SERVER_IP can be overridden by an environment variable.
SERVER_IP = os.environ.get("SERVER_IP", "")

if not SERVER_IP:
    print("Warning: SERVER_IP is not set. Please set it in your environment.")

def ask_with_params(message, params=None, timeout=15):
    """
    Send a message to the AI model with specific parameters.
    """
    try:
        # Load system prompt from file if it exists.
        prompt_path = os.path.join('txt_files', 'marie_system_prompt.txt')
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        else:
            system_prompt = "You are a helpful assistant."
    except Exception:
        system_prompt = "You are a helpful assistant."

    headers = {"Content-Type": "application/json"}
    base = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "temperature": 0.15,
        "top_p": 0.7,
        "n": 1,
        "stream": False,
        "max_output_tokens": 420,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.3,
        "seed": 42
    }

    if params:
        for k, v in params.items():
            if v is None and k in base:
                base.pop(k, None)
            else:
                base[k] = v

    try:
        response = requests.post(SERVER_IP, headers=headers, json=base, timeout=timeout)
        response.raise_for_status()
        response_json = response.json()
        reply = response_json['choices'][0]['message']['content']
    except Exception as e:
        body = None
        try:
            body = getattr(e, 'response', None) and e.response.text
        except Exception:
            body = None
        if body:
            reply = f"<ERROR: {e} -- server response: {body}>"
        else:
            reply = f"<ERROR: {e}>"

    return reply

def load_truthfulqa_data(path='benchmark_test/Yue-TruthfulQA.json'):
    """
    Load the TruthfulQA data from a JSON file.
    """
    if not os.path.exists(path):
        # Try relative to the script location if not found
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, 'Yue-TruthfulQA.json')
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading data: {e}")
        return []

def run_test():
    """
    Main entry point to run the TruthfulQA test.
    """
    data = load_truthfulqa_data()
    
    if not data:
        print("No data found in JSON.")
        return

    print(f"Found {len(data)} questions. Starting tests...")

    # Create results directory if it doesn't exist
    os.makedirs("results", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"results/yue_truthfulqa_results_{ts}.txt"

    with open(fname, "w", encoding="utf-8") as fh:
        fh.write(f"Yue-TruthfulQA Test Run: {datetime.datetime.now().isoformat()}\n\n")

        for i, item in enumerate(data):
            question = item.get("question", "Unknown Question")
            print(f"[{i+1}/{len(data)}] Testing: {question}")
            
            # Use only one temperature (0.15)
            reply = ask_with_params(question, params={"temperature": 0.15})
            
            # Write to file
            fh.write(f"Question {i+1}: {question}\n")
            fh.write(f"Reply: {reply}\n")
            fh.write("-" * 40 + "\n")
            
            # Print progress
            print(f"  Done.")

    print(f"\nSaved results to {fname}")

if __name__ == '__main__':
    run_test()
