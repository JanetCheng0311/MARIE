from langfuse import get_client
import dotenv
import lmstudio as lms
import os

# Load environment from .env (do NOT commit .env to git)
dotenv.load_dotenv()

# Read LMStudio / model-server host from environment. Prefer `SERVER_API_HOST`,
# fall back to `SERVER_IP` or `SERVER_HOST`. This avoids hard-coded hosts in code.
SERVER_API_HOST = os.environ.get("SERVER_API_HOST") or os.environ.get("SERVER_IP") or os.environ.get("SERVER_HOST")
if not SERVER_API_HOST:
    raise SystemExit("Error: SERVER_API_HOST (or SERVER_IP / SERVER_HOST) not set in environment")
def langfuse_test(input: str, output: str, model: str):
    langfuse = get_client()
    span = langfuse.start_observation(name="manual-span")
    span.update(input=input, output=output, model=model)
    
    span.end()

lms.configure_default_client(SERVER_API_HOST)

def test_lmstudio_call():
    model = lms.llm("google/gemma-3-27b")
    chat = lms.Chat("You are helper")

    chat.add_user_message("請用廣東話介紹一下自己。")

    response = model.respond(chat)
    print(type(response))
    print(response)
    print(response.content)
    print(response.model_info)

    langfuse_test(input="請用廣東話介紹一下自己。", output=str(response), model="openai/gpt-oss-20b")
    # print("Response:", response)

test_lmstudio_call()