import json
import time
from tqdm import tqdm
import pandas as pd

# OPTIONAL (for LLM judge)
from openai import OpenAI
import requests
from dotenv import load_dotenv

import os
from datetime import datetime
import json

load_dotenv()

client = OpenAI()  # make sure OPENAI_API_KEY is set

DATASET_PATH=os.getenv("DATASET_PATH","test_cases_derija.json")
API_URL=os.getenv("API_URL","http://localhost:8000/chat")

# ==============================
# 🔌 1. CONNECT YOUR RAG SYSTEM
# ==============================
def ask_bot(query: str) -> str:
    """
    Replace this with your actual RAG call
    Example:
        return rag_chain.invoke(query)
    """
    # TODO: CONNECT YOUR MODEL HERE
    res = requests.post(
        API_URL,
        json={"message": query}
    )
    return res.json()["response"]


# ==============================
# 🧪 2. LOAD DATASET
# ==============================
def load_dataset(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================
# ⚖️ 3. SIMPLE EVALUATION
# ==============================
def simple_score(expected, response):
    if expected is None:
        return False
    return expected.lower() in response.lower()


# ==============================
# 🤖 4. LLM-as-Judge (Recommended)
# ==============================
def llm_judge(query, expected, response):
    prompt = f"""
You are evaluating a chatbot answer.

User query: {query}
Expected answer: {expected}
Chatbot answer: {response}

Rules:
- Answer YES if the response is correct and grounded
- Answer NO if incorrect or hallucinated
- Be strict

Answer format:
YES or NO
"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        result = completion.choices[0].message.content.strip().upper()
        return "YES" in result

    except Exception as e:
        print("LLM judge error:", e)
        return False


# ==============================
# 📊 5. EVALUATION LOOP
# ==============================
def run_evaluation(dataset, use_llm_judge=False):
    results = []

    for test in tqdm(dataset):
        query = test["query"]
        expected = test.get("expected", "")

        response = ask_bot(query)

        if use_llm_judge:
            score = llm_judge(query, expected, response)
        else:
            score = simple_score(expected, response)

        results.append({
            "id": test["id"],
            "category": test.get("category"),
            "query": query,
            "expected": expected,
            "response": response,
            "correct": score
        })

        time.sleep(0.5)  # avoid rate limits

    return results


# ==============================
# 📈 6. METRICS
# ==============================
def compute_metrics(results):
    df = pd.DataFrame(results)

    accuracy = df["correct"].mean()

    by_category = df.groupby("category")["correct"].mean().to_dict()

    return {
        "accuracy": accuracy,
        "by_category": by_category
    }


# ==============================
# 💾 7. SAVE RESULTS
# ==============================


def save_results(results, dataset_path):
    # Extract dataset name without extension
    dataset_name = os.path.splitext(os.path.basename(dataset_path))[0]

    # Create timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create results filename
    results_filename = f"results_{dataset_name}_{timestamp}.json"

    # Optional: save inside "results" folder
    os.makedirs("results", exist_ok=True)

    full_path = os.path.join("results", results_filename)

    # Save file
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Results saved to: {full_path}")
# ==============================
# ▶️ 8. MAIN
# ==============================
if __name__ == "__main__":

    dataset = load_dataset(DATASET_PATH)

    print(f"Loaded {len(dataset)} test cases")

    results = run_evaluation(
        dataset,
        use_llm_judge=True  # 🔥 set False if no API
    )

    metrics = compute_metrics(results)

    print("\n📊 RESULTS")
    print("Accuracy:", round(metrics["accuracy"], 3))
    print("By Category:", metrics["by_category"])

    save_results(results, DATASET_PATH)

    print("\n✅ Results saved to results.json")