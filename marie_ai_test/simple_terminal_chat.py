import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use MARIE_API_KEY if available
API_KEY = os.environ.get("MARIE_API_KEY")

# Prefer SERVER_IP (usually full path) or fall back to SERVER_API_HOST
SERVER_URL = os.environ.get("SERVER_IP") or os.environ.get("SERVER_API_HOST")

# If it doesn't look like a full path, append the chat completions route
if SERVER_URL and not SERVER_URL.endswith("/chat/completions") and not SERVER_URL.endswith("/completions"):
    if "/api/v0" not in SERVER_URL:
        SERVER_URL = SERVER_URL.rstrip("/") + "/api/v0/chat/completions"
    else:
        SERVER_URL = SERVER_URL.rstrip("/") + "/chat/completions"

def chat_loop():
    if not SERVER_URL:
        print("Error: SERVER_API_HOST or SERVER_IP not found in .env file.")
        return

    print("--- MARIE Terminal Chat Bot ---")
    print(f"Connected to: {SERVER_URL}")
    print("Type 'exit' or 'quit' to end.")
    print("Press Enter on an empty line to send your message.\n")

    while True:
        try:
            print("You (multi-line, empty line to send):")
            lines = []
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
            
            user_input = "\n".join(lines).strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Goodbye!")
                break

            # Prepare the request payload
            payload = {
                "model": "openai/gpt-oss-20b",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": user_input}
                ],
                "temperature": 0.7,
                "max_tokens": 2048
            }
            
            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["Authorization"] = f"Bearer {API_KEY}"

            # Send request
            response = requests.post(SERVER_URL, headers=headers, json=payload, timeout=30)
            
            # Check for HTTP errors first
            if not response.ok:
                print(f"\nServer error ({response.status_code}): {response.text}\n")
                continue
                
            # Parse result
            data = response.json()
            
            if 'choices' in data:
                answer = data['choices'][0]['message']['content']
                print(f"\nAI: {answer}\n")
            elif 'error' in data:
                print(f"\nAI Server Error: {data['error']}\n")
            else:
                print(f"\nUnexpected server response format: {json.dumps(data, indent=2)}\n")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError connecting to AI server: {e}\n")

if __name__ == "__main__":
    chat_loop()
