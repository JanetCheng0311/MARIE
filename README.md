**MARIE**

- **Purpose:** A small demo harness to test Cantonese riddle/pun responses against simple assertions. This project also incorporates **SelfCheckGPT** for hallucination detection and fact-checking. Not production-ready — assertions and UI are a work in progress.

- **Files:**
  - `marie_test_ai.py`: main test runner.
  - `benchmark_test/`: contains Cantonese benchmark datasets and test scripts.
    - `Yue-TruthfulQA.json`: Cantonese version of TruthfulQA.
    - `yue_truthfulqa_test.py`: test script for Yue-TruthfulQA.
    - `SelfCheckGPT_test.py`: script demonstrating hallucination detection using SelfCheckGPT.
    - [benchmark_test/G-eval/g_eval_selfcheck_benchmark.py](benchmark_test/G-eval/g_eval_selfcheck_benchmark.py): g-eval style wrapper that runs `SelfCheckMQAG` (or a lightweight fallback) on items
      and writes JSON + summary files to `benchmark_test/G-eval/`.
  - `json_files/chinese_slang_questions.json`: riddle fixture.
  - `json_files/offensive_variants.json`: offensive Cantonese tokens used as safety triggers.
  - `txt_files/marie_system_prompt.txt`: system prompt used for chat requests (the code prefers this path).
  - `requirements.txt`: project dependencies (used by the quick setup).
  - `results/`: timestamped run logs (text).

- **Requirements:**
  - Python 3.9+ virtualenv (this project used a venv at `.venv`).
  - Packages listed in `requirements.txt` (e.g., `requests`, `gradio`, optionally `pycantonese`).

- **Quick setup:**

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Additional dependencies for the g-eval SelfCheck benchmark
---------------------------------------------------------
- If you want better sentence splitting (recommended) and `.docx` output, install into the project's venv:

```bash
# activate the project's venv first
.venv/bin/python -m pip install python-docx
.venv/bin/python -m pip install spacy
.venv/bin/python -m spacy download en_core_web_sm
```

Notes:
- The benchmark script will try to auto-add Spacy's `sentencizer` to avoid the common error:
  `ValueError: [E030] Sentence boundaries unset.` — if you still see that error, run
  `nlp.add_pipe('sentencizer')` in your pipeline or install a parser/senter component.
- Run the benchmark with the project's Python to ensure correct environment:

```bash
.venv/bin/python benchmark_test/G-eval/g_eval_selfcheck_benchmark.py --input path/to/items.json --output benchmark_test/G-eval/results.json
```

Output & interpretation
-----------------------
- The script writes a JSON results file and a `.txt` (or `.docx`) summary in the same folder as the output.
- Each item includes `scores` (sentence-level hallucination likelihoods) and a `verdict` determined by
  matching `metadata.true` / `metadata.false` labels: `PASS` / `FAIL` / `AMBIGUOUS`.
 - To prefer only `passage` matches (ignore `sampled_passages`) or change matching behavior, edit
   [benchmark_test/G-eval/g_eval_selfcheck_benchmark.py](benchmark_test/G-eval/g_eval_selfcheck_benchmark.py) (there are clear comments in the file explaining how).

**Audio / Voice Cloning**

- This repo includes scripts under `audio/` to create a cloned voice and to synthesize audio with it:
  - `audio/minimax_voice_clone_v2.py` — uploads sample audio, creates a cloned `voice_id` (uses MiniMax `voice_clone`).
  - `audio/use_cloned_voice.py` — generates TTS using a chosen `voice_id` (interactive selection supported).

- Environment variables used by the audio scripts (set in `.env`):
  - `MINIMAX_API_KEY` : your Minimax API key (required).
  - `MINIMAX_API_URL` : base Minimax API URL (defaults to `https://api.minimaxi.chat/v1`).
  - `MINIMAX_VOICE_IDS` : optional comma-separated list of voice ids to choose from in `use_cloned_voice.py`.
  - `MAX_VOICE_SAMPLE_SECONDS` : maximum total seconds of samples to include when creating a clone (default `300`).
  - `MAX_VOICE_SAMPLE_COUNT` : maximum number of files to include when creating a clone (default `7`).
  - `MINIMAX_CLONE_MODEL` : model used for cloning (default `speech-2.6-hd`).
  - `MINIMAX_CLONE_NOISE_REDUCTION` : `true|false` toggle to enable noise reduction on cloning (default `true`).
  - `MINIMAX_CLONE_NORMALIZE` : `true|false` to enable volume normalization (default `true`).
  - `MINIMAX_CLONE_PREVIEW_TEXT` : short preview text used to generate a demo audio when cloning.

- Quick cloning flow:

```bash
# Prepare samples: place multiple .wav/.mp3 files in audio/mp3_files/
cp .env.example .env
# edit .env to add MINIMAX_API_KEY and optionally MINIMAX_API_URL
/.venv/bin/python audio/minimax_voice_clone_v2.py
# script will select sample files (respecting MAX_VOICE_SAMPLE_SECONDS/COUNT), upload, and create a voice id
```

- Generate speech using a cloned voice (interactive selection if multiple voices available):

```bash
/.venv/bin/python audio/use_cloned_voice.py
# or specify voice and text
/.venv/bin/python audio/use_cloned_voice.py --voice-id ClonedVoice20260102174103 --text "測試粵語語音"
```

If you want higher fidelity, prefer clean 48k WAV samples and increase `MAX_VOICE_SAMPLE_SECONDS` or `MAX_VOICE_SAMPLE_COUNT` within limits imposed by the API.

- **Run demo:**

```bash
# run the riddle temperature sweep (creates a results file)
python marie_test_ai.py

# run the Yue-TruthfulQA benchmark
python benchmark_test/yue_truthfulqa_test.py

# run the SelfCheckGPT hallucination detection demo
python benchmark_test/SelfCheckGPT_test.py
```

- **Behavior:**
  - The runner loads the fixture from `json_files/` if present, otherwise falls back to root.
  - It queries the local chat endpoint defined in `marie_test_ai.py` (`SERVER_IP`) at 3 temperatures and saves replies and assertion results to `results/`.
  - Current assertions (demo): `is_cantonese`, `is_safe`, `concept_correct`, `answer_correct`. A run is considered PASS for a temperature when all four are True.

- **Customize:**
  - Edit `json_files/chinese_slang_questions.json` to add or change fixtures.
  - Edit `json_files/offensive_variants.json` to add Cantonese words/phrases that should mark a reply as unsafe.
  - To change where JSONs are loaded from, see `load_fixture()` and `load_offensive_variants()` in `marie_test_ai.py`.

- **Notes / Next steps:**
  - This is a demo. I plan to improve scoring, expose more assertion details in results (JSON), and add a small UI for selecting fixtures and thresholds.
  - **Audio Clone:** The `audio/audio_clone.py` script for voice cloning is currently not working and may require debugging or API updates.

If you want, I can:
- Run the script now and paste the run summary.
- Add JSON output alongside the text logs.
- Add a small CLI flag to choose fixture names.

**References / 資料來源**

- **SelfCheckGPT**: Used for hallucination detection and verifying model consistency.
  https://github.com/potsawee/selfcheckgpt

- Use of "100個粵語爛GAG (100 Cantonese Close-sounding Jokes)" — some questions in `json_files/chinese_slang_questions.json` were adapted from this collection:
  https://www.scribd.com/document/668283542/100%E5%80%8B%E7%B2%B5%E8%AA%9E%E7%88%9BGAG

  **說明（中文）**：部分題目取材或改編自上述集合，僅用作測試與示範用途；如需正式發布，請確認原始作者授權。

**Using environment variables / 使用環境變數**

- Copy `.env.example` to `.env` and fill in values you need (e.g., `SERVER_IP`). Do NOT commit `.env` to version control.

```bash
cp .env.example .env
# edit .env and fill your keys
```

- `marie_test_ai.py` will use the `SERVER_IP` environment variable if present. You can also export it in your shell:

```
