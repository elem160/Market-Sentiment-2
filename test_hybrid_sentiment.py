import pandas as pd
import numpy as np
import time
import os
from transformers import pipeline
from dotenv import load_dotenv
from openai import OpenAI
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

load_dotenv()
openrouter_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key) if openrouter_key else None
MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"

def verify_sentiment_batch(sentences):
    if not client or not sentences:
        return ["neutral"] * len(sentences)
        
    prompt = ""
    for i, s in enumerate(sentences):
        prompt += f"{i+1}. {s}\n"
        
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are an expert financial sentiment classifier. Given a numbered list of financial sentences, determine the sentiment of EACH sentence as POSITIVE, NEGATIVE, or NEUTRAL.\nReply ONLY with lines matching the format:\n1: POSITIVE\n2: NEUTRAL\n3: NEGATIVE\nDo not provide any explanation or extra text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        
        # Parse output
        results = {}
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line:
                parts = line.split(':')
                num_str = parts[0].strip()
                label = parts[1].strip().lower()
                if num_str.isdigit():
                    idx = int(num_str) - 1
                    if "pos" in label:
                        results[idx] = "positive"
                    elif "neg" in label:
                        results[idx] = "negative"
                    else:
                        results[idx] = "neutral"
                        
        # Fill in any missing indices with neutral as safe fallback
        final_labels = []
        for i in range(len(sentences)):
            final_labels.append(results.get(i, "neutral"))
        return final_labels
    except Exception as e:
        print(f"  [!] Error calling OpenRouter: {e}")
        return ["neutral"] * len(sentences)

def main():
    print("====================================================================")
    print("     HYBRID SYSTEM VALIDATION: FINBERT + NEMOTRON SENTIMENT         ")
    print("====================================================================\n")
    
    csv_path = os.path.join("Sentiment Dataset", "data.csv")
    if not os.path.exists(csv_path):
        print(f"[!] Could not find dataset at {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=['Sentence', 'Sentiment'])
    df['Sentiment'] = df['Sentiment'].str.lower().str.strip()
    
    # We take a stratified random sample of 1,000 sentences for rapid evaluation
    sample_size = min(1000, len(df))
    print(f"[*] Creating stratified random sample of {sample_size} sentences from Kaggle dataset...")
    df_sample = df.groupby('Sentiment', group_keys=False).apply(lambda x: x.sample(int(np.rint(sample_size * len(x)/len(df))), random_state=42))
    
    sentences = df_sample['Sentence'].tolist()
    ground_truth = df_sample['Sentiment'].tolist()
    
    print(f"[*] Running Stage 1: FinBERT Sentiment Classification...")
    t0 = time.time()
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    
    finbert_preds = []
    results = sentiment_pipeline(sentences, batch_size=32)
    for res in results:
        finbert_preds.append(res['label'].lower())
        
    acc_stage1 = accuracy_score(ground_truth, finbert_preds)
    print(f"[+] Stage 1 Complete in {time.time() - t0:.2f} seconds! FinBERT Accuracy: {acc_stage1*100:.2f}%\n")
    
    # Stage 2: Nemotron verifies & corrects directional predictions
    print("[*] Running Stage 2: Nemotron Sentiment Verifier & Corrector...")
    print("    Taking all sentences predicted as POSITIVE or NEGATIVE by FinBERT and sending to Nemotron to confirm or correct the label...")
    
    hybrid_preds = list(finbert_preds) # Start with finbert predictions
    directional_indices = [i for i, p in enumerate(finbert_preds) if p in ['positive', 'negative']]
    directional_sentences = [sentences[i] for i in directional_indices]
    
    print(f"[*] Evaluating {len(directional_sentences)} directional sentences with Nemotron in batches of 50...")
    t1 = time.time()
    
    batch_size = 50
    corrections_made = 0
    
    for start_idx in range(0, len(directional_sentences), batch_size):
        end_idx = min(start_idx + batch_size, len(directional_sentences))
        batch_sents = directional_sentences[start_idx:end_idx]
        batch_indices = directional_indices[start_idx:end_idx]
        
        nemo_labels = verify_sentiment_batch(batch_sents)
        
        for k, orig_idx in enumerate(batch_indices):
            new_label = nemo_labels[k]
            old_label = finbert_preds[orig_idx]
            if new_label != old_label:
                corrections_made += 1
            hybrid_preds[orig_idx] = new_label
        time.sleep(0.5)
        
    print(f"[+] Stage 2 Complete in {time.time() - t1:.2f} seconds! Nemotron corrected {corrections_made} predictions.\n")
    
    acc_hybrid = accuracy_score(ground_truth, hybrid_preds)
    print("====================================================================")
    print(f"               HYBRID SYSTEM ACCURACY COMPARISON                    ")
    print("====================================================================")
    print(f"Stage 1 (Pure FinBERT Alone):      {acc_stage1*100:.2f}% Accuracy")
    print(f"Stage 2 (Hybrid FinBERT+Nemotron): {acc_hybrid*100:.2f}% Accuracy")
    print(f"Absolute Accuracy Change:          {(acc_hybrid - acc_stage1)*100:+.2f}%\n")
    
    print("Detailed Classification Report (Hybrid System):")
    print(classification_report(ground_truth, hybrid_preds, target_names=['negative', 'neutral', 'positive'], digits=4))
    
    print("Confusion Matrix (Hybrid System) [Rows: True Label, Cols: Predicted Label]:")
    labels_order = ['negative', 'neutral', 'positive']
    cm = confusion_matrix(ground_truth, hybrid_preds, labels=labels_order)
    cm_df = pd.DataFrame(cm, index=[f"True_{l}" for l in labels_order], columns=[f"Pred_{l}" for l in labels_order])
    print(cm_df.to_string())
    print("====================================================================\n")

if __name__ == "__main__":
    main()
