# Langfuse Logview Instructions

To view the results of your Cantonese transcription and correction runs effectively in Langfuse, follow these steps to configure your dashboard:

## Column Setup
In the **Observations** or **Generations** table, click the "Columns" button and ensure the following fields are visible:

1.  **Model**: Shows which AI model performed the correction (e.g., `openai/gpt-oss-20b`).
2.  **Metadata -> trans_time_s**: The time taken by the Gradio API for the initial audio-to-text transcription.
3.  **Metadata -> correction_time_s**: The time taken by the AI model to refine the script.
4.  **Input**: The original audio filename (e.g., `20250226_2_1.mp3`).
5.  **Output**: The corrected Cantonese script (refined version only).

## Filtering
You can filter by **Name** to distinguish between steps:
-   `transcript-raw`: The initial output from the Gradio/Whisper API.
-   `transcript-correction`: The refined output from the LLMs.

## Sorting
-   Sort by **Start Time** to see the most recent runs.
-   Sort by **correction_time_s** (if numeric column) to compare model speeds.

## Grouping
If you are running many models for one file, you can filter by `Metadata -> audio` equal to your filename (e.g., `20250226_2_1.mp3`) to see all variations for that specific clip in one view.
