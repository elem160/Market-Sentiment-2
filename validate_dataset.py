import pandas as pd
import numpy as np
import time
import os
import json
from transformers import pipeline
from dotenv import load_dotenv
from openai import OpenAI
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

load_dotenv()
openrouter_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key) if openrouter_key else None
MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"

def batch_verify_catalysts(sentences):
    if not client or not sentences:
        return list(range(1, len(sentences) + 1))
        
    prompt = ""
    for i, s in enumerate(sentences):
        prompt += f"{i+1}. {s}\n"
        
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a financial expert filtering noise. Given the following numbered list of sentences, identify ONLY the ones that are true market-moving catalysts (e.g., earnings beat/miss, major M&A, regulatory changes, material product news, macroeconomic data). Ignore opinion, speculation, clickbait, and routine noise. Reply ONLY with a comma-separated list of the numbers corresponding to the catalysts. For example: 1, 4, 15. If absolutely NONE are catalysts, reply with NONE. Do not provide any other text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        if content.upper() == "NONE":
            return []
            
        catalyst_indices = []
        for num_str in content.replace('\n', ',').split(','):
            num_str = num_str.strip()
            if num_str.isdigit():
                catalyst_indices.append(int(num_str))
        return catalyst_indices
    except Exception as e:
        print(f"  [!] Error calling OpenRouter: {e}")
        return list(range(1, len(sentences) + 1))

def main():
    print("====================================================================")
    print("       FINANCIAL SENTIMENT DATASET ARCHITECTURE VALIDATION          ")
    print("====================================================================\n")
    
    csv_path = os.path.join("Sentiment Dataset", "data.csv")
    if not os.path.exists(csv_path):
        print(f"[!] Could not find dataset at {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=['Sentence', 'Sentiment'])
    df['Sentiment'] = df['Sentiment'].str.lower().str.strip()
    
    print(f"[*] Total rows in dataset: {len(df)}")
    print("    Class distribution:")
    for label, count in df['Sentiment'].value_counts().items():
        print(f"      - {label.upper()}: {count} ({count/len(df)*100:.1f}%)")
        
    # We take a stratified random sample of 1,000 sentences for rapid, statistically robust evaluation
    sample_size = min(1000, len(df))
    print(f"\n[*] Creating stratified random sample of {sample_size} sentences for evaluation...")
    df_sample = df.groupby('Sentiment', group_keys=False).apply(lambda x: x.sample(int(np.rint(sample_size * len(x)/len(df))), random_state=42))
    
    print(f"[*] Sample ready! Running Stage 1: FinBERT Sentiment Classification...")
    t0 = time.time()
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    
    sentences = df_sample['Sentence'].tolist()
    ground_truth = df_sample['Sentiment'].tolist()
    
    # Run FinBERT inference in batches
    predictions = []
    confidences = []
    
    results = sentiment_pipeline(sentences, batch_size=32)
    for res in results:
        predictions.append(res['label'].lower())
        confidences.append(res['score'])
        
    elapsed_finbert = time.time() - t0
    print(f"[+] Stage 1 Complete in {elapsed_finbert:.2f} seconds ({len(sentences)/elapsed_finbert:.1f} sentences/sec)!\n")
    
    # Calculate accuracy metrics
    acc = accuracy_score(ground_truth, predictions)
    print("====================================================================")
    print(f"               STAGE 1: FINBERT SENTIMENT ACCURACY                  ")
    print("====================================================================")
    print(f"Overall Accuracy: {acc*100:.2f}%\n")
    print("Detailed Classification Report:")
    print(classification_report(ground_truth, predictions, target_names=['negative', 'neutral', 'positive']))
    print("Confusion Matrix [Rows: True Label, Cols: Predicted Label]:")
    labels_order = ['negative', 'neutral', 'positive']
    cm = confusion_matrix(ground_truth, predictions, labels=labels_order)
    cm_df = pd.DataFrame(cm, index=[f"True_{l}" for l in labels_order], columns=[f"Pred_{l}" for l in labels_order])
    print(cm_df.to_string())
    print("====================================================================\n")
    
    # Stage 2: Nemotron Catalyst Verification on directional predictions
    print("[*] Running Stage 2: Nemotron Catalyst Verification...")
    print("    We now test what happens when we send FinBERT's POSITIVE and NEGATIVE predictions to Nemotron to filter out noise/opinion.")
    
    directional_indices = [i for i, p in enumerate(predictions) if p in ['positive', 'negative']]
    directional_sentences = [sentences[i] for i in directional_indices]
    directional_preds = [predictions[i] for i in directional_indices]
    
    print(f"[*] FinBERT flagged {len(directional_sentences)} directional sentences. Verifying in batches of 50...")
    
    verified_catalyst_flags = [False] * len(directional_sentences)
    batch_size = 50
    t1 = time.time()
    
    for start_idx in range(0, len(directional_sentences), batch_size):
        end_idx = min(start_idx + batch_size, len(directional_sentences))
        batch_sents = directional_sentences[start_idx:end_idx]
        cat_nums = batch_verify_catalysts(batch_sents)
        for num in cat_nums:
            if 1 <= num <= len(batch_sents):
                verified_catalyst_flags[start_idx + (num - 1)] = True
        time.sleep(0.5) # Gentle rate limiting
        
    elapsed_nemo = time.time() - t1
    verified_count = sum(verified_catalyst_flags)
    filtered_count = len(directional_sentences) - verified_count
    
    print(f"[+] Stage 2 Complete in {elapsed_nemo:.2f} seconds!\n")
    print("====================================================================")
    print("           STAGE 2: NEMOTRON CATALYST NOISE FILTERING               ")
    print("====================================================================")
    print(f"Total Directional Sentences Evaluated: {len(directional_sentences)}")
    print(f"Verified True Market Catalysts:        {verified_count} ({verified_count/len(directional_sentences)*100:.1f}%)")
    print(f"Filtered Out as Opinion/Routine Noise: {filtered_count} ({filtered_count/len(directional_sentences)*100:.1f}%)")
    
    print("\n--- EXAMPLES OF VERIFIED MARKET CATALYSTS (Accepted by Nemotron) ---")
    accepted_examples = [s for i, s in enumerate(directional_sentences) if verified_catalyst_flags[i]][:5]
    for s in accepted_examples:
        print(f"  [✓] {s}")
        
    print("\n--- EXAMPLES OF OPINION/ROUTINE NOISE (Filtered out by Nemotron) ---")
    rejected_examples = [s for i, s in enumerate(directional_sentences) if not verified_catalyst_flags[i]][:5]
    for s in rejected_examples:
        print(f"  [✗] {s}")
    print("====================================================================\n")

if __name__ == "__main__":
    main()
