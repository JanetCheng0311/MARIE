# MARIE AI Testing System
# MARIE AI 測試系統
# This script tests the model's ability to answer Cantonese riddles (爛GAG) 
# while checking for language, safety, and conceptual correctness.
# 此腳本測試模型回答廣東話爛 GAG 的能力，同時檢查語言、安全性和概念正確性。

import gradio as gr
import requests
import os
import datetime
import json
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Optional Cantonese helper library.
# 選用的廣東話輔助庫。
try:
    import pycantonese as pc
    _HAS_PYCANTONESE = True
    print("pycantonese available")
except Exception:
    pc = None
    _HAS_PYCANTONESE = False
    print("pycantonese not installed; continuing without it")


# SERVER_IP can be overridden by an environment variable or a .env file.
# `SERVER_IP` env var example: http://YOUR_IP:PORT/api/v0/chat/completions
SERVER_IP = os.environ.get("SERVER_IP", "")

if not SERVER_IP:
    print("Warning: SERVER_IP is not set. Please set it in your .env file.")

def ask_with_params(message, params=None, timeout=15):
    """
    Send a message to the AI model with specific parameters.
    使用特定參數向 AI 模型發送訊息。
    """
    try:
        # Load system prompt from file.
        # 從文件載入系統提示詞。
        alt_prompt = os.path.join('txt_files', 'marie_system_prompt.txt')
        prompt_path = alt_prompt if os.path.exists(alt_prompt) else 'marie_system_prompt.txt'
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
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

    # Override default parameters if provided.
    # 如果提供了參數，則覆蓋默認參數。
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
        # If server returned a response body, include it to help debugging (e.g., bad schema).
        body = None
        try:
            body = getattr(e, 'response', None) and e.response.text
        except Exception:
            body = None
        if body:
            reply = f"<ERROR: {e} -- server response: {body}>"
        else:
            reply = f"<ERROR: {e}>"

    print(reply)
    return reply


def yes(message, history):
    """
    Simple wrapper for Gradio interface.
    Gradio 介面的簡單包裝函數。
    """
    return ask_with_params(message)


def run_temperature_sweep(temperatures=None, question=None, fixture=None):
    """
    Query the model at several temperatures, score each reply, and record the results.
    在多個溫度下查詢模型，為每個回覆評分並記錄結果。
    """
    if temperatures is None:
        temperatures = [0.15, 0.5, 0.9]

    # Load fixture data if not provided.
    # 如果未提供，則載入測試數據。
    if fixture is None:
        fixture = load_fixture()
    
    if question is None:
        question = fixture.get("question")

    results = []
    for t in temperatures:
        params = {"temperature": t, "top_p": 0.95, "n": 1, "seed": None}
        reply = ask_with_params(question, params=params)
        
        # Build assertions for the reply.
        # 為回覆建立斷言（檢查項）。
        assertions = build_assertions(reply, fixture)
        
        # Scoring logic: sum the four core checks: cantonese, safe, concept_correct, answer_correct.
        # 評分邏輯：加總四項核心檢查：廣東話、安全、概念正確、答案正確。
        score = sum(1 for k in ("is_cantonese", "is_safe", "concept_correct", "answer_correct") if assertions.get(k))
        
        results.append({"temperature": t, "reply": reply, "assertions": assertions, "score": score})

        # Print detailed score breakdown to console.
        # 在控制台打印詳細評分細節。
        print(f"  Temp {t}: Score {score}/4 ({'PASS' if score == 4 else 'FAIL'})")
        print(f"    is_cantonese: {assertions.get('is_cantonese')}")
        print(f"    is_safe: {assertions.get('is_safe')}")
        print(f"    concept_correct: {assertions.get('concept_correct')} (mentions_keyword: {assertions.get('mentions_keyword')})")
        print(f"    answer_correct: {assertions.get('answer_correct')}")
        print(f"    Reply preview: {reply[:100]!r}")
        print()

    # Print summary to console.
    # 在控制台打印摘要。
    print("\nTemperature sweep results:")
    for r in results:
        status = "PASS" if r['score'] == 4 else "FAIL"
        print(f"- temp={r['temperature']}: score={r['score']}/4 {status} reply_preview={r['reply'][:80]!r}")

    # Write results to a timestamped text file.
    # 將結果寫入帶有時間戳的文本文件。
    try:
        os.makedirs("results", exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"results/marie_results_{ts}.txt"
        with open(fname, "w", encoding="utf-8") as fh:
            fh.write(f"MARIE Temperature Sweep Run: {datetime.datetime.now().isoformat()}\n")
            fh.write(f"Question: {question}\n\n")
            for r in results:
                fh.write(f"Temperature: {r['temperature']}\n")
                fh.write(f"Score (is_cantonese + is_safe + concept_correct + answer_correct): {r['score']}/4\n")
                fh.write("Assertions:\n")
                
                # Write core assertions.
                # 寫入核心斷言。
                core_keys = ("is_cantonese", "is_safe", "concept_correct", "answer_correct")
                for k in core_keys:
                    fh.write(f"  {k}: {r['assertions'].get(k)}\n")
                
                # Write other assertions (like not_answering_present) without duplication.
                # 寫入其他斷言（如 not_answering_present），避免重複。
                for k, v in r['assertions'].items():
                    if k not in core_keys:
                        fh.write(f"  {k}: {v}\n")
                
                fh.write("Reply:\n")
                fh.write(r['reply'] + "\n")
                fh.write("-" * 40 + "\n")
        print(f"Saved results to {fname}")
    except Exception as e:
        print(f"Failed to write results file: {e}")

    return results


def build_assertions(reply, fixture):
    """
    Scoring logic for the model's reply.
    評分邏輯：檢查模型回覆是否符合各項指標。
    """
    text = (reply or "").strip()
    assertions = {}

    # 1) Cantonese Check / 廣東話檢查
    # Check for common Cantonese particles to ensure the reply is in Cantonese.
    # 檢查常用廣東話助詞，確保回覆使用廣東話。
    cantonese_indicators = ["係", "因為", "聽", "喺", "咁", "咪", "冇", "佢哋", "嘅", "啦", "呀"]
    assertions["is_cantonese"] = any(tok in text for tok in cantonese_indicators)

    # 2) Safety Check / 安全檢查
    # Ensure the reply does not contain offensive variants.
    # 確保回覆不包含冒犯性詞彙。
    # Use the centralized `OFFENSIVE_VARIANTS` list (loaded from offensive_variants.json).
    # 使用從 `offensive_variants.json` 載入的集中列表 `OFFENSIVE_VARIANTS`。
    offensive_list = OFFENSIVE_VARIANTS
    offensive_present = any(o and o in text for o in offensive_list)
    assertions["is_safe"] = not offensive_present

    # 3) Concept Correctness / 概念正確性
    # Check if the reply contains the exact wording from the 'concept' field.
    # 檢查回覆是否包含 'concept' 欄位中的精確字眼。
    concept_list = fixture.get("concept", [])
    keyword_list = fixture.get("keyword", [])
    # Require: (a) all exact concept wordings present, AND (b) at least one exact keyword present.
    # 要求：(a) 回覆需包含所有 concept 中的精確字眼，且 (b) 至少包含 keyword 中的一個精確字眼。
    has_all_concepts = all((c in text) for c in concept_list) if concept_list else False
    mentions_keyword = any((k in text) for k in keyword_list) if keyword_list else False
    # expose keyword-related details for inspection/debugging
    assertions["mentions_keyword"] = mentions_keyword
    assertions["matched_keywords"] = [k for k in keyword_list if k in text]
    assertions["concept_correct"] = has_all_concepts and mentions_keyword

    # 4) Answer Correctness / 答案正確性
    # Check if the reply points to the correct answer (from 'true' list) and avoids 'false' list.
    # 檢查回覆是否指向正確答案（來自 'true' 列表）並避開 'false' 列表。
    true_list = fixture.get("true", [])
    false_list = fixture.get("false", [])
    
    # Check if any true answer is mentioned in a way that claims it's the answer.
    # 檢查是否以「答案係...」等方式提到正確答案。
    answer_claims_list = fixture.get("answer_claims", [])
    if not answer_claims_list:
        for t in true_list:
            answer_claims_list.extend([f"答案係{t}", f"係{t}", f"答係{t}"])
    
    has_true = any(t in text for t in true_list)
    has_claim = any(a in text for a in answer_claims_list)
    has_false = any(f in text for f in false_list)
    
    assertions["answer_correct"] = (has_true or has_claim) and (not has_false)

    # Note: 'not_answering' detection removed — scoring no longer treats it specially.
    # 註：已移除 'not_answering' 檢測 — 評分不再將其作為特殊處理。

    return assertions


def load_fixture(name='default', path='chinese_slang_questions.json'):
    """
    Load a single test fixture from a JSON file.
    從 JSON 文件載入單個測試數據。
    """
    fixtures = load_all_fixtures(path=path)
    if not fixtures:
        return {}
    
    # If a specific name is requested, try to find it (though load_all_fixtures flattens them).
    # This is a bit of a shim for the old behavior.
    return fixtures[0]


def load_all_fixtures(path='chinese_slang_questions.json'):
    """
    Load all test fixtures from a JSON file, flattening nested groups.
    從 JSON 文件載入所有測試數據，並展開嵌套群組。
    """
    fixtures = []
    try:
        alt_path = os.path.join('json_files', os.path.basename(path))
        use_path = alt_path if os.path.exists(alt_path) else path
        if not os.path.exists(use_path):
            return []
            
        with open(use_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if not isinstance(data, dict):
            return []

        # Recursive search for dicts with 'question'
        def find_fixtures(obj):
            if isinstance(obj, dict):
                if 'question' in obj:
                    fixtures.append(obj)
                else:
                    for v in obj.values():
                        find_fixtures(v)
        
        find_fixtures(data)
    except Exception as e:
        print(f"Error loading fixtures: {e}")
        
    return fixtures


def load_offensive_variants(path='offensive_variants.json'):
    """
    Load a list of offensive variants from a JSON file.
    從 JSON 文件載入冒犯性詞彙列表。
    """
    try:
        alt_path = os.path.join('json_files', os.path.basename(path))
        use_path = alt_path if os.path.exists(alt_path) else path
        with open(use_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # If the file contains an object, try to find the first list value.
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
    except Exception:
        pass
    return []


# Load offensive variants at module import.
# 在模組匯入時載入冒犯性詞彙。
OFFENSIVE_VARIANTS = load_offensive_variants()


def run_riddle_test():
    """
    Main entry point to run the riddle test for all fixtures.
    執行謎題測試的主入口，針對所有測試數據。
    """
    fixtures = load_all_fixtures()
    
    if not fixtures:
        print("No fixtures found in JSON.")
        return []

    all_results = []
    temperatures = [0.15, 0.5, 0.9]
    
    print(f"Found {len(fixtures)} fixtures. Starting tests...")

    for i, fixture in enumerate(fixtures):
        q = fixture.get("question", "Unknown Question")
        print(f"\n[{i+1}/{len(fixtures)}] Testing: {q}")
        results = run_temperature_sweep(temperatures=temperatures, question=q, fixture=fixture)
        all_results.append({
            "question": q,
            "results": results
        })

    return all_results


if __name__ == '__main__':
    run_riddle_test()
