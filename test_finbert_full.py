import pandas as pd
import time
import os
from transformers import pipeline
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

def main():
    print("====================================================================")
    print("         PURE FINBERT BENCHMARK ON FULL DATASET (5,842 ROWS)        ")
    print("====================================================================\n")
    
    csv_path = os.path.join("Sentiment Dataset", "data.csv")
    if not os.path.exists(csv_path):
        print(f"[!] Could not find dataset at {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=['Sentence', 'Sentiment'])
    df['Sentiment'] = df['Sentiment'].str.lower().str.strip()
    
    print(f"[*] Total valid rows in dataset: {len(df)}")
    print("    Ground Truth Class Distribution:")
    for label, count in df['Sentiment'].value_counts().items():
        print(f"      - {label.upper()}: {count} ({count/len(df)*100:.1f}%)")
        
    print(f"\n[*] Loading local FinBERT NLP model (ProsusAI/finbert)...")
    t0 = time.time()
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    print(f"[+] Model loaded in {time.time() - t0:.2f} seconds.")
    
    sentences = df['Sentence'].tolist()
    ground_truth = df['Sentiment'].tolist()
    
    print(f"[*] Running FinBERT inference on ALL {len(sentences)} sentences... (This takes ~3 minutes)")
    t1 = time.time()
    
    predictions = []
    confidences = []
    
    # Process in batches of 64 for optimal speed
    results = sentiment_pipeline(sentences, batch_size=64)
    for res in results:
        predictions.append(res['label'].lower())
        confidences.append(res['score'])
        
    elapsed = time.time() - t1
    print(f"[+] Inference Complete in {elapsed:.2f} seconds ({len(sentences)/elapsed:.1f} sentences/sec)!\n")
    
    # Calculate accuracy metrics
    acc = accuracy_score(ground_truth, predictions)
    print("====================================================================")
    print(f"              PURE FINBERT FULL DATASET RESULTS                     ")
    print("====================================================================")
    print(f"Total Sentences Evaluated: {len(sentences)}")
    print(f"Overall Accuracy:          {acc*100:.2f}%\n")
    
    print("Detailed Classification Report:")
    print(classification_report(ground_truth, predictions, target_names=['negative', 'neutral', 'positive'], digits=4))
    
    print("Confusion Matrix [Rows: True Label, Cols: Predicted Label]:")
    labels_order = ['negative', 'neutral', 'positive']
    cm = confusion_matrix(ground_truth, predictions, labels=labels_order)
    cm_df = pd.DataFrame(cm, index=[f"True_{l}" for l in labels_order], columns=[f"Pred_{l}" for l in labels_order])
    print(cm_df.to_string())
    print("====================================================================\n")
    
    # Analysis of predicted distribution vs true distribution
    df['Predicted'] = predictions
    df['Confidence'] = confidences
    
    print("Predicted Class Distribution vs Ground Truth:")
    for label in labels_order:
        true_cnt = sum(1 for g in ground_truth if g == label)
        pred_cnt = sum(1 for p in predictions if p == label)
        print(f"  - {label.upper()}: True = {true_cnt} ({true_cnt/len(df)*100:.1f}%) | Predicted = {pred_cnt} ({pred_cnt/len(df)*100:.1f}%)")
        
    print("\n[*] Benchmark complete!")

if __name__ == "__main__":
    main()
