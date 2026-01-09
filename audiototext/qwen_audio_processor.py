import os
import sys
import time
import subprocess
import argparse
import requests
import json
import tempfile
import shutil
from datetime import datetime

try:
    from gradio_client import Client, handle_file
except ImportError:
    print("Error: gradio_client is not installed. Please install it using 'pip install gradio_client'.")
    sys.exit(1)

def get_audio_duration(file_path):
    """Returns the duration of the audio file in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting duration for {file_path}: {e}")
        return 0

def split_audio(file_path, output_dir, segment_length=30):
    """Splits the audio file into segments of specified length using ffmpeg."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    output_pattern = os.path.join(output_dir, f"{base_name}_%03d.mp3")
    
    # We use segment muxer to split audio into chunks without re-encoding if possible
    cmd = [
        "ffmpeg", "-y", "-i", file_path, "-f", "segment", "-segment_time", str(segment_length),
        "-c", "copy", output_pattern
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error splitting audio: {e}")
        return []
    
    segments = sorted([os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith(base_name) and f.endswith(".mp3")])
    return segments

def transcribe_segment(audio_path, gradio_url, api_name):
    """Transcribes a single audio segment using the Gradio API.

    Returns a tuple: (text_str, raw_result).
    Retries on transient errors and respects long-running transcription latencies.
    """
    max_retries = 4
    # Retry creating the Client itself (it fetches the app config on init)
    client = None
    for attempt in range(1, max_retries + 1):
        try:
            client = Client(gradio_url)
            break
        except Exception as e:
            err_str = str(e)
            print(f"Client init attempt {attempt}/{max_retries} failed for {gradio_url}: {err_str}")
            if attempt == max_retries:
                return "", {"error": err_str}
            wait = min(10, 2 ** attempt)
            time.sleep(wait)
    for attempt in range(1, max_retries + 1):
        try:
            # gradio_client handle_file accepts local paths or URLs
            result = client.predict(audio=handle_file(audio_path), api_name=api_name)

            raw = result
            if isinstance(result, (list, tuple)):
                text = result[0]
            elif isinstance(result, dict):
                text = result.get("text") or result.get("result") or str(result)
            else:
                text = str(result)
            return text, raw
        except Exception as e:
            err_str = str(e)
            print(f"Transcription attempt {attempt}/{max_retries} failed for {audio_path}: {err_str}")
            if attempt == max_retries:
                return "", {"error": err_str}
            # exponential backoff
            wait = min(30, 2 ** attempt)
            print(f"Retrying in {wait}s...")
            time.sleep(wait)


def contains_cjk(text: str, min_count: int = 3) -> bool:
    """Return True if text contains at least `min_count` CJK Unified Ideographs."""
    if not text:
        return False
    import re
    matches = re.findall(r"[\u4e00-\u9fff]", text)
    return len(matches) >= min_count

def refine_with_qwen(text, server_url, model_name):
    """Refines the text using Qwen via the specified server IP endpoint."""
    system_prompt = (
        "你是一位粵語專家。請將下列語音轉文字稿精修为流暢的繁體中文（粵語口語習慣），特別修正同音字錯誤。\n"
        "要求：\n"
        "1. 只回傳最終精修後的文字，禁止包含任何解釋、步驟或「思考過程」(<thought>)。\n"
        "2. 保持用字為繁體中文（香港常用字形），絕不使用簡體字。\n"
        "3. 確保語氣自然，符合粵語口語（保留「嘅」、「㗎」、「咧」等助詞）。\n"
        "4. 直接輸出文稿內容，不要有任何前綴（如「以下是精修後的文稿：」）。\n"
    )
    
    # Send the transcript as the user message, with an explicit label to help the model
    user_message = f"[TRANSCRIPT]\n{text}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.2,
        "max_tokens": 4096
    }
    
    headers = {"Content-Type": "application/json"}
    start_time = time.time()
    try:
        response = requests.post(server_url, headers=headers, json=payload, timeout=300)
        elapsed = time.time() - start_time
        response.raise_for_status()
        result = response.json()
        
        # Handle different potential response formats (OpenAI-like or custom)
        if "choices" in result:
            refined_text = result["choices"][0]["message"]["content"]
        else:
            refined_text = result.get("output") or result.get("result") or json.dumps(result)
            
        # Remove "thinking" part if present (often wrapped in <thought> or similar tags)
        import re
        refined_text = re.sub(r"<thought>.*?</thought>", "", refined_text, flags=re.DOTALL)
        # Also remove common thinking markers like "Thinking: ..."
        refined_text = re.sub(r"Thinking:.*?\n", "", refined_text, flags=re.IGNORECASE)
        
        return refined_text.strip(), elapsed
    except Exception as e:
        print(f"Refinement error: {e}")
        return f"Error during refinement: {e}", time.time() - start_time


def compare_scripts(server_url: str, model_name: str, true_script: str, refined_script: str) -> tuple[str, float]:
    """Ask the model to compare the true script and the refined script and summarize differences (in Traditional Chinese).

    Returns (comparison_text, elapsed_seconds).
    """
    system = (
        "你是一位粵語文本比對與評分專家（繁體中文，香港常用字形）。\n"
        "任務：請以原始稿件（TRUE）為基準，評估並打分精修後稿件（REFINED）的品質。\n"
        "評分要點（請務必考量，並在輸出中顯示數值）：\n"
        "1) 準確性（是否保留原意、數字、人名、地點等關鍵資訊）權重 40%。\n"
        "2) 可讀性與流暢度（斷句、標點、語序）權重 25%。\n"
        "3) 粵語語氣與口語保留（接受像「嘅」「㗎」「咧」等粵語助詞，視語境判斷是否保留）權重 20%。\n"
        "4) 同音/近音字修正與錯字率（是否正確修正 ASR 錯字）權重 15%。\n"
        "請輸出：\n"
        "- 一個總分（0-100），並附上每個評分要點的子分與說明。\n"
        "- 列出最重要的 5 個具體差異（要點式，每點一行），並指出該差異是否可接受（例如：保留「嘅」屬可接受範圍）。\n"
        "- 最後給出一個簡短建議（不超過兩行），說明如何改善精修稿以更接近原稿。\n"
        "只回傳上述結果，使用繁體中文，不要包含呼叫或流程說明。"
    )

    user = (
        "原始稿件（TRUE）:\n" + true_script + "\n\n精修後稿件（REFINED）:\n" + refined_script
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.0,
        "max_tokens": 1200,
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    start = time.time()
    try:
        resp = requests.post(server_url, headers=headers, json=payload, timeout=180)
        elapsed = time.time() - start
        resp.raise_for_status()
        j = resp.json()
        reply = j.get("choices", [{}])[0].get("message", {}).get("content")
        if reply is None:
            reply = j.get("result") or j.get("output") or json.dumps(j, ensure_ascii=False)
    except Exception as e:
        reply = f"<ERROR comparing scripts: {e}>"
        elapsed = time.time() - start
    return reply, elapsed


def translate_comparison_to_english(server_url: str, model_name: str, chinese_text: str) -> tuple[str, float]:
    """Translate the Chinese comparison text into clear, concise English while preserving scores and bullets.

    Returns (english_text, elapsed_seconds).
    """
    system = (
        "You are a professional translator. Translate the following Traditional Chinese evaluation text into clear, concise English. "
        "Preserve numeric scores, bullet lists, and any important labels. Output only the English translation, without extra commentary."
    )
    user = chinese_text

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0.0,
        "max_tokens": 1200,
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    start = time.time()
    try:
        resp = requests.post(server_url, headers=headers, json=payload, timeout=180)
        elapsed = time.time() - start
        resp.raise_for_status()
        j = resp.json()
        reply = j.get("choices", [{}])[0].get("message", {}).get("content")
        if reply is None:
            reply = j.get("result") or j.get("output") or json.dumps(j, ensure_ascii=False)
    except Exception as e:
        reply = f"<ERROR translating comparison: {e}>"
        elapsed = time.time() - start
    return reply, elapsed

def main():
    parser = argparse.ArgumentParser(description="Transcribe audio via Gradio and refine via Qwen server.")
    parser.add_argument("--audio", required=False, help="Path to the audio file to process. If omitted you'll be prompted to choose an MP3 from mp3_audio or fallback folders.")
    parser.add_argument(
        "--gradio-url",
        default=os.environ.get("GRADIO_URL", "https://work.manakin-gecko.ts.net:8443/"),
        help="URL of the Gradio transcription service (can also set GRADIO_URL env var).",
    )
    parser.add_argument("--api-name", default="/transcribe", help="Gradio API endpoint name (default: /transcribe).")
    parser.add_argument("--server-ip", default="http://100.66.65.36:1234/v1/chat/completions", help="The server IP/URL for Qwen refinement.")
    parser.add_argument("--model", default="qwen/qwen3-30b-a3b", help="Model name for refinement (default: qwen/qwen3-30b-a3b).")
    parser.add_argument("--compare-model", default="openai/gpt-oss-20b", help="Model name to use for comparison/scoring (default: openai/gpt-oss-20b).")
    parser.add_argument("--output-dir", default=None, help="Directory to save the result. Defaults to STTresults/timestamp.")
    
    args = parser.parse_args()
    
    def find_mp3_candidates():
        # Search multiple potential folders for MP3 files
        candidates = []
        search_dirs = [
            os.path.join(os.getcwd(), "mp3_audio"),
            os.path.join(os.getcwd(), "audiototext", "mp3_audio"),
            os.path.join(os.getcwd(), "audio", "mp3_files"),
            os.path.join(os.path.dirname(__file__), "mp3_audio")
        ]
        
        seen_paths = set()
        for folder in search_dirs:
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    if name.lower().endswith(".mp3"):
                        full_path = os.path.abspath(os.path.join(folder, name))
                        if full_path not in seen_paths:
                            candidates.append(full_path)
                            seen_paths.add(full_path)
        return candidates

    def find_true_script_candidates(audio_path=None):
        """Search for .txt files containing 'true script' or 'true_script'."""
        candidates = []
        search_dirs = [
            os.path.join(os.getcwd(), "mp3_audio"),
            os.path.join(os.getcwd(), "audiototext", "mp3_audio"),
            os.path.join(os.getcwd(), "audio", "mp3_files"),
            os.path.join(os.path.dirname(__file__), "mp3_audio")
        ]
        if audio_path:
            search_dirs.insert(0, os.path.dirname(audio_path))

        seen_paths = set()
        for folder in search_dirs:
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    lname = name.lower()
                    if (".txt" in lname) and ("true script" in lname or "true_script" in lname or "truescript" in lname):
                        full_path = os.path.abspath(os.path.join(folder, name))
                        if full_path not in seen_paths:
                            candidates.append(full_path)
                            seen_paths.add(full_path)
        return candidates

    input_audio = args.audio
    if not input_audio:
        candidates = find_mp3_candidates()
        if not candidates:
            print("No MP3 files found in 'mp3_audio', 'audiototext/mp3_audio', or 'audio/mp3_files'.")
            print("Please provide an audio file path using --audio /path/to/file.mp3")
            return
        print("Select an audio file to process:")
        for i, p in enumerate(candidates, start=1):
            # Display relative to current dir for brevity if possible
            try:
                display_path = os.path.relpath(p)
            except Exception:
                display_path = p
            print(f"{i}. {display_path}")
        sel_audio = None
        try:
            choice = input("Enter number (or filename) to choose: ").strip()
        except Exception:
            print("No interactive input available; please provide --audio path.")
            return
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(candidates):
                sel_audio = candidates[idx]
        else:
            for p in candidates:
                if os.path.basename(p) == choice or os.path.relpath(p) == choice:
                    sel_audio = p
                    break
        if not sel_audio:
            print("Invalid selection. Exiting.")
            return
        input_audio = sel_audio

    # New: Allow user to choose a true script for rating
    true_script_text = None
    ts_candidates = find_true_script_candidates(input_audio)
    
    if ts_candidates:
        print("\nSelect a (true script) file for comparison/rating (or skip):")
        for i, p in enumerate(ts_candidates, start=1):
            try:
                display_path = os.path.relpath(p)
            except Exception:
                display_path = p
            print(f"{i}. {display_path}")
        print("0. Skip comparison")
        print("Enter. Auto-detect (find matching filename)")
        
        try:
            ts_choice = input("Enter number or path: ").strip()
            if ts_choice == "0":
                print("Comparison explicitly skipped by user.")
                true_script_text = False # Use False as a sentinel for explicit skip
            elif ts_choice == "":
                # Fall through to auto-detect logic below
                pass
            elif ts_choice.isdigit():
                idx = int(ts_choice) - 1
                if 0 <= idx < len(ts_candidates):
                    sel_path = ts_candidates[idx]
                    with open(sel_path, "r", encoding="utf-8") as tf:
                        true_script_text = tf.read().strip()
                    print(f"Selected: {os.path.basename(sel_path)}")
            else:
                # Try to match by filename or check if path exists
                matched_path = None
                for cand in ts_candidates:
                    if ts_choice == os.path.basename(cand) or ts_choice == os.path.relpath(cand):
                        matched_path = cand
                        break
                
                final_path = matched_path or (ts_choice if os.path.exists(ts_choice) else None)
                
                if final_path:
                    with open(final_path, "r", encoding="utf-8") as tf:
                        true_script_text = tf.read().strip()
                    print(f"Using: {os.path.basename(final_path)}")
                else:
                    print(f"Could not find or match script: {ts_choice}. Will try auto-detect.")
        except Exception as e:
            print(f"Error during selection: {e}")
    else:
        print("\nNo (true script) files found in search paths. Will try auto-detecting matching file.")

    input_audio = os.path.abspath(input_audio)
    if not os.path.exists(input_audio):
        print(f"File not found: {input_audio}")
        return

    base_name = os.path.splitext(os.path.basename(input_audio))[0]

    # Set up results directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output_dir:
        results_dir = args.output_dir
    else:
        # Put results under the common audiototext/STTresults folder (parent of choppedmp3_x)
        results_dir = os.path.join(os.path.dirname(os.path.dirname(input_audio)), "STTresults", timestamp)
    
    os.makedirs(results_dir, exist_ok=True)
    
    # 1. Check duration and chop if > 30s
    duration = get_audio_duration(input_audio)
    print(f"Processing audio: {os.path.basename(input_audio)} ({duration:.2f}s)")
    
    temp_dir = tempfile.mkdtemp()
    try:
        if duration > 30:
            print("Audio > 30s. Splitting into 30s chunks for best quality...")
            segments = split_audio(input_audio, temp_dir, segment_length=30)
        else:
            print("Audio <= 30s. Processing as single file.")
            segments = [input_audio]
            
        # 2. Transcribe each segment
        transcriptions = []
        raw_results = []
        total_stt_time = 0

        print(f"Transcribing {len(segments)} segment(s)...")
        for i, seg in enumerate(segments):
            start = time.time()
            text, raw = transcribe_segment(seg, args.gradio_url, args.api_name)
            total_stt_time += (time.time() - start)
            raw_results.append({"segment": os.path.basename(seg), "raw": raw})
            if text:
                transcriptions.append(text.strip())
            print(f"  [{i+1}/{len(segments)}] Transcribed.")

        full_transcript = " ".join(transcriptions)

        # Save raw STT transcript and API responses
        try:
            stt_file = os.path.join(results_dir, f"{base_name}.stt_raw.{timestamp}.txt")
            with open(stt_file, "w", encoding="utf-8") as sf:
                sf.write(full_transcript)
            raw_json_file = os.path.join(results_dir, f"{base_name}.stt_api_responses.{timestamp}.json")
            with open(raw_json_file, "w", encoding="utf-8") as rj:
                json.dump(raw_results, rj, ensure_ascii=False, indent=2)
            print(f"Saved STT transcript to: {stt_file}")
            print(f"Saved raw API responses to: {raw_json_file}")
        except Exception as e:
            print(f"Failed to save STT/raw responses: {e}")
        
        # Try to find a local true script file if one wasn't selected manually
        if true_script_text is None:
            # Check both (true script) and (true_script) formats
            candidates = [
                os.path.join(os.path.dirname(input_audio), f"{base_name}(true script).txt"),
                os.path.join(os.path.dirname(input_audio), f"{base_name}(true_script).txt")
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    try:
                        with open(candidate, "r", encoding="utf-8") as tf:
                            true_script_text = tf.read().strip()
                        print(f"Found auto-detected true script: {candidate}")
                        break
                    except Exception as e:
                        print(f"Failed to read true script file: {e}")
            
        # 3. Refine with Qwen
        # IMPORTANT: do NOT give the true script to Qwen. Always send only the STT transcript to Qwen.
        # If STT is empty and true_script_text exists, we will NOT send true_script_text to Qwen.
        if full_transcript.strip():
            print(f"Refining text with {args.model} at {args.server_ip}...")
            refined_text, refinement_time = refine_with_qwen(full_transcript, args.server_ip, args.model)
        else:
            # Try to find an existing Qwen-refined file from previous runs to compare.
            refined_text = None
            refinement_time = 0.0
            # search results directory siblings for previous qwen_refined files matching base_name
            search_dir = os.path.join(os.path.dirname(input_audio), "STTresults")
            if os.path.isdir(search_dir):
                candidates = []
                for root, dirs, files in os.walk(search_dir):
                    for fn in files:
                        if fn.startswith(base_name) and "qwen_refined" in fn and fn.endswith(".txt"):
                            candidates.append(os.path.join(root, fn))
                candidates.sort(key=os.path.getmtime, reverse=True)
                if candidates:
                    try:
                        with open(candidates[0], "r", encoding="utf-8") as rf:
                            # try to extract the body after the header divider
                            body = rf.read()
                            parts = body.split("\n" + "="*40 + "\n\n", 1)
                            refined_text = parts[1] if len(parts) > 1 else body
                        print(f"Loaded previous Qwen refined file for comparison: {candidates[0]}")
                    except Exception as e:
                        print(f"Failed to read previous refined file: {e}")
            if refined_text is None and true_script_text:
                # As a last resort, create a local normalized candidate from true_script (but do NOT send it to Qwen).
                print("No previous Qwen refined file found; creating a local normalized candidate from true script for comparison (Qwen will NOT see the true script).")
                # very small normalization: collapse repeated characters and remove filler markers
                import re
                normalized = re.sub(r"[\s]+", " ", true_script_text)
                normalized = re.sub(r"(嗯|啊|嘛){2,}", "", normalized)
                refined_text = normalized
        
        # 4. Save results to txt file
        base_name = os.path.splitext(os.path.basename(input_audio))[0]
        output_file = os.path.join(results_dir, f"{base_name}.qwen_refined.{timestamp}.txt")
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"--- Result for Model: {args.model} ---\n")
            f.write(f"Audio API Runtime: {total_stt_time:.2f}s\n")
            f.write(f"AI Correction Runtime: {refinement_time:.2f}s\n")
            f.write(f"Saved to: {output_file}\n")
            f.write("="*40 + "\n\n")
            f.write(refined_text)
            
        print(f"\nDone! Results saved to: {output_file}")
        print(f"Audio API Runtime: {total_stt_time:.2f}s")
        print(f"AI Refinement Runtime: {refinement_time:.2f}s")
        
        # 5. Compare true script (if available) with refined script using GPT model
        # If a true script file exists, always run the GPT comparison (do not send the true script to Qwen).
        # We check if it's a non-empty string.
        if isinstance(true_script_text, str) and true_script_text.strip() and refined_text:
            print(f"\nComparing true script and refined script via GPT model ({args.compare_model})...")
            compare_text, compare_time = compare_scripts(args.server_ip, args.compare_model, true_script_text, refined_text)
            compare_file = os.path.join(results_dir, f"{base_name}.comparison.{timestamp}.txt")
            
            try:
                with open(compare_file, "w", encoding="utf-8") as cf:
                    cf.write(f"--- Comparison for Model: {args.compare_model} ---\n")
                    cf.write(f"AI Comparison Runtime: {compare_time:.2f}s\n")
                    cf.write(f"Saved to: {compare_file}\n")
                    cf.write("="*40 + "\n\n")
                    cf.write(compare_text)
                print(f"Comparison saved to: {compare_file}")
                
                # Print a small snippet of the comparison to terminal so the user sees it immediately
                print("\n--- GPT Rating Summary ---")
                # Extract score if possible (simple heuristic)
                for line in compare_text.split("\n")[:10]:
                    if "分" in line or "score" in line.lower():
                        print(line)
                print("-" * 25)

                # Also request an English translation of the comparison and save it
                try:
                    print(f"Translating comparison to English via {args.compare_model}...")
                    en_text, en_time = translate_comparison_to_english(args.server_ip, args.compare_model, compare_text)
                    en_file = os.path.join(results_dir, f"{base_name}.comparison.en.{timestamp}.txt")
                    with open(en_file, "w", encoding="utf-8") as ef:
                        ef.write(f"--- English Translation (Model: {args.compare_model}) ---\n")
                        ef.write(f"Translation Runtime: {en_time:.2f}s\n")
                        ef.write(f"Saved to: {en_file}\n")
                        ef.write("="*40 + "\n\n")
                        ef.write(en_text)
                    print(f"English translation saved to: {en_file}")
                except Exception as e:
                    print(f"Failed to translate comparison to English: {e}")
            except Exception as e:
                print(f"Failed to save comparison results: {e}")
        elif true_script_text is False:
            print("\nComparison skipped: Explicitly disabled by user selection.")
        elif not true_script_text:
            print("\nComparison skipped: No true script (content was empty or not provided).")
        elif not refined_text:
            print("\nComparison skipped: No refined text available to compare.")

        print(f"\nProcess complete. All files saved to: {results_dir}")
        print("-" * 40)
        for f_name in sorted(os.listdir(results_dir)):
            print(f" - {f_name}")
        
    finally:
        # Cleanup temp chunks
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    main()
