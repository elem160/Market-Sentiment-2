"""Benchmark comparing unbatched sequential FinBERT inference vs batched FinBERTScorer.

Demonstrates >= 1.8x throughput improvement on identical hardware.
Run via:
    python scripts/bench_finbert.py
"""
import asyncio
import os
import sys
import time

# Ensure offline cache is used if offline
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
from app.config import settings
from app.services.scoring import FinBERTScorer

SAMPLE_HEADLINES = [
    ("Apple reports record quarterly revenue and exceptional iPhone demand", "Net income exceeded analyst estimates by 15%."),
    ("Federal Reserve signals potential rate hikes to combat persistent inflation", "Markets fell as bond yields climbed across maturities."),
    ("Tesla vehicle deliveries drop below expectations amid supply chain bottlenecks", "Operating margins contracted 200 basis points."),
    ("Microsoft cloud revenue surges 30% propelled by artificial intelligence adoption", "Azure customer growth reaccelerated in Q3."),
    ("Amazon announces major logistics cost cuts and workforce reduction", "Shares gained 4% in extended trading on profitability outlook."),
    ("Nvidia unveils next-generation Blackwell GPU architecture with massive performance gains", "Enterprise preorder backlog reaches record levels."),
    ("Oil prices plunge 5% as global demand outlook deteriorates", "Energy sector equities led market declines."),
    ("Alphabet reports strong Google Cloud profitability and search ad resilience", "Operating cash flow topped $28 billion."),
    ("Meta operating income doubles on AI-driven ad efficiency and user growth", "Family of apps daily active people reached 3.2 billion."),
    ("JPMorgan raises net interest income guidance following regional banking consolidation", "Credit loss provisions remained benign."),
    ("Boeing halts aircraft deliveries following factory quality control inspection failures", "Cash burn projection worsened for the fiscal year."),
    ("Eli Lilly diabetes and weight loss drugs surpass $5 billion in quarterly sales", "Manufacturing capacity expansion underway across three sites."),
    ("Intel suspends dividend and announces 15% headcount reduction to fund fab buildout", "Shares suffered steepest single-day drop in four decades."),
    ("Walmart raises full-year sales guidance citing grocery market share gains", "Consumer spending remained resilient across household income cohorts."),
    ("Salesforce beats profit projections but billings growth slows to single digits", "Subscription renewals showed extended sales cycle friction."),
    ("Disney theme park operating margins soften as domestic consumer attendance moderates", "Streaming division turned profitable for the first time."),
]


async def run_benchmark():
    # Use 32 articles (representative retained batch)
    full_sample = SAMPLE_HEADLINES * 2
    count = len(full_sample)
    print(f"=== FinBERT Inference Benchmark ({count} Articles) ===")
    print(f"Model: {settings.FINBERT_MODEL_NAME}")
    print(f"Batch Size: {settings.FINBERT_BATCH_SIZE}\n")

    # 1. Warm-up / Load model
    print("Loading model and tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(settings.FINBERT_MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(settings.FINBERT_MODEL_NAME)
    pipe = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer, top_k=None, device=-1)

    # Warmup both sequential and batched paths
    w_text = f"{full_sample[0][0]}. {full_sample[0][1]}"[:500]
    pipe(w_text)
    pipe([w_text, w_text], batch_size=2)
    print("Warmup complete.\n")

    # 2. Baseline: Legacy behavior (encode/decode round-trip + sequential unbatched inference)
    print("Running Baseline: Legacy sequential unbatched loop with encode/decode round trip...")
    t0 = time.perf_counter()
    baseline_results = []
    for title, summary in full_sample:
        combined = f"{title}. {summary}".strip()
        tokens = tokenizer.encode(combined, max_length=512, truncation=True)
        prepared = tokenizer.decode(tokens, skip_special_tokens=True)
        out = pipe(prepared)[0]
        baseline_results.append(out)
    t_baseline = time.perf_counter() - t0
    ms_per_article_baseline = (t_baseline / count) * 1000.0
    print(f"  Total time: {t_baseline:.3f} s")
    print(f"  Latency: {ms_per_article_baseline:.1f} ms / article\n")

    # 3. Batched Inference via FinBERTScorer (clean lead_text, batched pipeline)
    print(f"Running Optimized: Batched inference via FinBERTScorer (batch_size={settings.FINBERT_BATCH_SIZE})...")
    scorer = FinBERTScorer.get_instance()
    scorer._pipeline = pipe
    scorer.state = "LOADED"

    lead_texts = [f"{title}. {summary}".strip()[:500] for title, summary in full_sample]
    t1 = time.perf_counter()
    batched_results = await scorer.score(lead_texts)
    t_batched = time.perf_counter() - t1
    ms_per_article_batched = (t_batched / count) * 1000.0
    print(f"  Total time: {t_batched:.3f} s")
    print(f"  Latency: {ms_per_article_batched:.1f} ms / article\n")

    # 4. Results & Speedup Factor
    speedup = t_baseline / max(t_batched, 0.0001)
    print("=== Results Summary ===")
    print(f"Baseline (Sequential): {ms_per_article_baseline:.1f} ms / article ({t_baseline:.3f} s total)")
    print(f"Batched (FinBERTScorer): {ms_per_article_batched:.1f} ms / article ({t_batched:.3f} s total)")
    print(f"Throughput Speedup: {speedup:.2f}x")

    if speedup >= 1.8:
        print(f"SUCCESS: Achieved {speedup:.2f}x speedup (>= 1.8x requirement)!")
    else:
        print(f"Note: Speedup was {speedup:.2f}x (baseline requirement: 1.8x)")

    scorer.shutdown()
    return speedup


if __name__ == "__main__":
    asyncio.run(run_benchmark())
