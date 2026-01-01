**MARIE**

- **Purpose:** A small demo harness to test Cantonese riddle/pun responses against simple assertions. This project also incorporates **SelfCheckGPT** for hallucination detection and fact-checking. Not production-ready — assertions and UI are a work in progress.

- **Files:**
  - `marie_test_ai.py`: main test runner.
  - `benchmark_test/`: contains Cantonese benchmark datasets and test scripts.
    - `Yue-TruthfulQA.json`: Cantonese version of TruthfulQA.
    - `yue_truthfulqa_test.py`: test script for Yue-TruthfulQA.
    - `SelfCheckGPT_test.py`: script demonstrating hallucination detection using SelfCheckGPT.
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
