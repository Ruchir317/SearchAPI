# SearchAPI Fact Verification

This project automates fact verification using Google's Custom Search API and Gemini AI. It retrieves web evidence for factual claims and uses LLMs to determine truthfulness.

## Features
- Article search + summarization
- Gemini-based fact analysis
- Batch processing of thousands of claims
- Output in structured JSON format

## Setup
1. Create a `.env` file with:
    ```
    GEMINI_API_KEY=your_key
    GOOGLE_API_KEY=your_key
    GOOGLE_CSE_ID=your_id
    ```

2. Install dependencies:
    ```
    pip install -r requirements.txt

    PS - If it is asking for more than requirements.txt has then run

    pip install -r all_requirements.txt
    ```

3. Run the verifier:
    ```
    python batch_fact_verifier.py --start 0 --end 5000

    Or you can run

    python run_and_push.py

    Which will push the files to github for you
    ```
