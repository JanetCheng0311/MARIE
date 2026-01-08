from langfuse import get_client
import dotenv
import lmstudio as lms
import os
from urllib.parse import urlparse
import json
from pathlib import Path

# Load environment from .env (do NOT commit .env to git)
dotenv.load_dotenv()

# Read LMStudio / model-server host from environment. Prefer `SERVER_API_HOST`,
# fall back to `SERVER_IP` or `SERVER_HOST`. This avoids hard-coded hosts in code.
server_raw = os.environ.get("SERVER_API_HOST") or os.environ.get("SERVER_IP") or os.environ.get("SERVER_HOST")
if not server_raw:
    raise SystemExit("Error: SERVER_API_HOST (or SERVER_IP / SERVER_HOST) not set in environment")

# Normalize host: accept full URLs or host:port and strip any path
parsed = urlparse(server_raw)
if parsed.scheme and parsed.netloc:
    api_host = parsed.netloc
else:
    api_host = server_raw
def langfuse_test(input: str, output: str, model_name: str, model_info: dict | None = None):
    langfuse = get_client()
    # Use a generation-type observation so Langfuse shows model details in the UI.
    try:
        span = langfuse.start_observation(
            name="manual-span",
            as_type="generation",
            input=input,
            output=output,
            model=model_name,
            metadata=model_info,
        )
    except Exception:
        # Fallback to a basic span if generation-type not supported
        span = langfuse.start_observation(name="manual-span", input=input, output=output)

    span.end()

lms.configure_default_client(api_host)

def test_lmstudio_call():
    model = lms.llm("google/gemma-2-27b")
    # Load the system prompt from the local prompt file so it isn't hard-coded here
    prompt_path = os.path.join(os.path.dirname(__file__), "marie_humorai_prompt.txt")
    with open(prompt_path, "r", encoding="utf-8") as pf:
        system_prompt = pf.read()

    # Load questions from JSON file
    qpath = os.path.join(os.path.dirname(__file__), '..', 'json_files', 'chinese_humor_questions.json')
    try:
        with open(qpath, 'r', encoding='utf-8') as jf:
            questions_obj = json.load(jf)
    except Exception as e:
        raise SystemExit(f"Error loading questions JSON: {e}")

    # Iterate categories and their items, send each 'question' field to the model
    # Load offensive variants to filter/replace in model outputs
    offensives = []
    ov_path = Path(os.path.join(os.path.dirname(__file__), '..', 'json_files', 'offensive_variants.json'))
    if ov_path.exists():
        try:
            with ov_path.open('r', encoding='utf-8') as f:
                offensives = json.load(f)
        except Exception:
            offensives = []
    for category, items in questions_obj.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if not isinstance(entry, dict):
                continue
            q = entry.get('question')
            if not q:
                continue

            print(f"---{category}/{key}---")
            chat = lms.Chat(system_prompt)
            chat.add_user_message(q)
            try:
                response = model.respond(chat)
            except Exception as e:
                print(f"Error from model for {key}: {e}")
                continue

            # Get the model's main content
            try:
                out_text = response.content
            except Exception:
                out_text = str(response)

            # Replace offensive variants with a safe placeholder
            if offensives and isinstance(out_text, str):
                for bad in offensives:
                    if not bad:
                        continue
                    out_text = out_text.replace(bad, '[言語被替換]')

            print(out_text)

            # Extract model_info if available and record to langfuse so the UI shows model metadata
            model_info = None
            try:
                model_info = getattr(response, 'model_info', None) or getattr(response, 'model_info', None)
            except Exception:
                model_info = None

            try:
                # Use the filtered output for logging
                langfuse_test(input=q, output=out_text, model_name="google/gemma-3-27b", model_info=model_info)
            except Exception:
                pass

test_lmstudio_call()