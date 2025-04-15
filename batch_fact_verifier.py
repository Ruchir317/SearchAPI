import os
import json
import re
import time
import requests
import argparse
import multiprocessing
from newspaper import Article
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google import genai
from google.genai import types
from tqdm import tqdm
import nltk

load_dotenv()

# ENVIRONMENT VARIABLES
API_KEY = os.getenv("GEMINI_API_KEY")
CSE_ID = os.getenv("GOOGLE_CSE_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# CONFIGURATION
INPUT_FILE = "data/politifact_factcheck_data.json"
OUTPUT_DIR = "output"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
ERROR_LOG_FILE = os.path.join(OUTPUT_DIR, "error_log.txt")

# Ensure output folder exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# OUTPUT CONTAINERS
all_fact_results = []
all_full_outputs = []
all_parsed_outputs = []

# RESUME CHECKPOINT
def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_checkpoint(done_ids):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(done_ids), f, indent=2)

# INPUT DATA
def load_statements(file_path, limit):
    with open(file_path, "r", encoding="utf-8") as f:
        return [(i, json.loads(line)["statement"]) for i, line in enumerate(f) if i < limit]

# GOOGLE SEARCH
def google_search(query, api_key, cse_id, num=10):
    service = build("customsearch", "v1", developerKey=api_key)
    res = service.cse().list(q=query, cx=cse_id, num=num).execute()
    return res.get("items", [])

# ARTICLE SUMMARIZATION
def _extract_summary(url, return_dict):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        article = Article(url)
        article.set_html(response.text)
        article.parse()
        article.nlp()

        return_dict["summary"] = article.summary
    except Exception as e:
        return_dict["summary"] = None

def summarize_article(url, timeout=10):
    manager = multiprocessing.Manager()
    return_dict = manager.dict()

    proc = multiprocessing.Process(target=_extract_summary, args=(url, return_dict))
    proc.start()
    proc.join(timeout)

    if proc.is_alive():
        print(f"⛔ Timeout exceeded for: {url}")
        proc.terminate()
        proc.join()
        return None

    return return_dict.get("summary", None)

def filter_top_articles(articles, top_k=10):
    scored = []
    for a in articles:
        summary = a.get("summary", "")
        if summary and len(summary.strip()) >= 200:
            scored.append((len(summary.strip()), a))
    return [a for _, a in scored[:top_k]]

# PROMPT BUILDING
def build_input_from_fact(fact, articles):
    input_str = f"**Factual Claim:**\n{fact}\n\n**Relevant Articles:**\n"
    for i, article in enumerate(articles, 1):
        input_str += f"\nArticle {i}:\n"
        input_str += f"- **Title:** {article['title']}\n"
        input_str += f"- **URL:** {article['url']}\n"
        input_str += f"- **Snippet:** {article['snippet']}\n"
        input_str += f"- **Summary:** {article['summary']}\n"
    return input_str

# PARSING
def extract_section(header, text):
    pattern = rf"\*\*{header}:\*\*\s*(.*?)(?=\n\*\*|$)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else None

def extract_bullet_list(header, text):
    section = extract_section(header, text)
    return re.findall(r"[*\-]\s+(.*)", section) if section else []

# GEMINI
def run_gemini_verification(prompt_text, fact):
    client = genai.Client(api_key=API_KEY)
    model = "gemini-2.0-flash"
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])]

    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="text/plain",
        system_instruction=[
            types.Part.from_text(text="""You are an automated fact-verification assistant. You will be given a structured input that contains:

- A factual claim at the top
- A list of summarized news articles that are relevant to that claim.

You must return:

**Verdict:** True or False  
**Collective Summary:** Overall what the sources say  
**Reasoning:** 2–4 sentence justification  
**Sources Summary:** Bullet list of titles with one-line context

Only use the provided summaries. Be objective. Format your output in Markdown.""")
        ]
    )

    full_response = ""
    for chunk in client.models.generate_content_stream(
        model=model, contents=contents, config=config
    ):
        full_response += chunk.text

    return full_response.strip()

# PROCESS EACH FACT
def process_fact(index, fact, done_ids):
    if index in done_ids:
        return  # skip processed

    articles_raw = google_search(fact, GOOGLE_API_KEY, CSE_ID, num=10)
    enriched = []

    for result in articles_raw:
        url = result.get("link")
        summary = summarize_article(url)
        if summary:
            enriched.append({
                "title": result.get("title"),
                "url": url,
                "snippet": result.get("snippet"),
                "summary": summary
            })
        time.sleep(1)

    top_articles = filter_top_articles(enriched, top_k=6)
    if not top_articles:
        raise ValueError("No valid articles found.")

    all_fact_results.append({
        "fact": fact,
        "articles": top_articles
    })

    prompt = build_input_from_fact(fact, top_articles)
    gemini_output = run_gemini_verification(prompt, fact)

    all_full_outputs.append({
        "fact": fact,
        "gemini_output": gemini_output
    })

    parsed = {
        "fact": fact,
        "verdict": extract_section("Verdict", gemini_output),
        "collective_summary": extract_section("Collective Summary", gemini_output),
        "reasoning": extract_section("Reasoning", gemini_output),
        "sources_summary": extract_bullet_list("Sources Summary", gemini_output)
    }

    all_parsed_outputs.append(parsed)
    done_ids.add(index)

# FINAL SAVE
def save_all_outputs():
    def load_existing(path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def merge_unique(existing, new, key="fact"):
        seen = set()
        merged = []

        for item in existing + new:
            k = item.get(key)
            if k and k not in seen:
                merged.append(item)
                seen.add(k)
        return merged

    fact_path = os.path.join(OUTPUT_DIR, "fact_results.json")
    full_path = os.path.join(OUTPUT_DIR, "full_output.json")
    parsed_path = os.path.join(OUTPUT_DIR, "parsed_output.json")

    merged_facts = merge_unique(load_existing(fact_path), all_fact_results)
    merged_full = merge_unique(load_existing(full_path), all_full_outputs)
    merged_parsed = merge_unique(load_existing(parsed_path), all_parsed_outputs)

    with open(fact_path, "w", encoding="utf-8") as f:
        json.dump(merged_facts, f, ensure_ascii=False, indent=2)

    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(merged_full, f, ensure_ascii=False, indent=2)

    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(merged_parsed, f, ensure_ascii=False, indent=2)

# ERROR LOGGING
def log_error(index, fact, error):
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{index}] {fact[:100]}... → {str(error)}\n")

# MAIN
def run_verification_batch(start_idx=0, end_idx=10):
    initial_done = load_checkpoint()

    all_statements = load_statements(INPUT_FILE, end_idx)
    statements = [(i, fact) for i, fact in all_statements if start_idx <= i < end_idx]

    done_ids = load_checkpoint()

    for index, fact in tqdm(statements, total=len(statements)):
        try:
            process_fact(index, fact, done_ids)
            save_checkpoint(done_ids)
            save_all_outputs()  # ✅ Save after each successful iteration
        except Exception as e:
            log_error(index, fact, e)
            continue

    print(f"\n✅ Done! Processed range {start_idx}–{end_idx}")
    print(f"🧠 Previously done: {len(initial_done)} | Newly saved: {len(done_ids) - len(initial_done)}")

# CLI entry point
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=10)
    args = parser.parse_args()

    run_verification_batch(start_idx=args.start, end_idx=args.end)