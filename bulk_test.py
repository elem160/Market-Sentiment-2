import json
from transformers import pipeline
import simple_scraper
import warnings
import os

warnings.filterwarnings("ignore")

# Define 80 instruments
instruments = {
    "Stocks": [
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", 
        "GOOGL", "META", "NFLX", "JPM", "V", 
        "WMT", "PG", "UNH", "HD", "MA", 
        "BAC", "DIS", "CVX", "KO", "PEP"
    ],
    "Forex": [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", 
        "USD/CHF", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY", 
        "AUD/JPY", "EUR/CHF", "EUR/AUD", "GBP/AUD", "USD/MXN", 
        "USD/ZAR", "USD/SGD", "USD/HKD", "EUR/CAD", "GBP/CAD"
    ],
    "Commodities": [
        "Gold", "Silver", "Crude Oil", "Brent Crude", "Natural Gas", 
        "Copper", "Corn", "Wheat", "Soybeans", "Coffee", 
        "Sugar", "Cotton", "Cocoa", "Palladium", "Platinum", 
        "Aluminum", "Zinc", "Nickel", "Lead", "Lean Hogs"
    ],
    "Futures": [
        "ES=F", "NQ=F", "YM=F", "RTY=F", "CL=F", 
        "GC=F", "SI=F", "ZC=F", "ZW=F", "ZS=F", 
        "SB=F", "CT=F", "KC=F", "HG=F", "NG=F", 
        "ZB=F", "ZN=F", "ZF=F", "ZT=F", "HE=F"
    ]
}

# Silence stdout temporarily
import sys
class DummyFile(object):
    def write(self, x): pass
    def flush(self): pass

def fetch_and_analyze(ticker, sentiment_pipeline):
    save_stdout = sys.stdout
    sys.stdout = DummyFile()
    
    # Fetch news
    yahoo_news = simple_scraper.get_yahoo_finance_news(ticker)
    sources = ["Reuters", "Bloomberg", "CNBC", "Wall Street Journal", "MarketWatch", "Seeking Alpha", "Motley Fool"]
    rss_news = []
    for source in sources:
        rss_news.extend(simple_scraper.get_google_rss_news(ticker, source))
        
    all_news = yahoo_news + rss_news
    
    total_score = 0.0
    valid_articles = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0
    
    for item in all_news:
        text = item["text"]
        truncated_text = text[:512] 
        try:
            result = sentiment_pipeline(truncated_text)[0]
            label = result['label']
            score = result['score']
            
            if label == 'positive':
                total_score += score
                positive_count += 1
            elif label == 'negative':
                total_score -= score
                negative_count += 1
            else:
                neutral_count += 1
                
            valid_articles += 1
        except Exception:
            pass
            
    sys.stdout = save_stdout
    
    if valid_articles == 0:
        return None
        
    average_score = total_score / valid_articles
    
    return {
        "ticker": ticker,
        "valid_articles": valid_articles,
        "positive": positive_count,
        "negative": negative_count,
        "neutral": neutral_count,
        "average_score": average_score
    }

def main():
    print("[*] Loading FinBERT model...")
    sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    print("[*] Model loaded. Starting bulk test...")
    
    results = []
    
    for category, tickers in instruments.items():
        print(f"\n--- Testing Category: {category} ---")
        for ticker in tickers:
            print(f"Testing {ticker}...", end=" ", flush=True)
            res = fetch_and_analyze(ticker, sentiment_pipeline)
            if res:
                results.append({**res, "category": category})
                print(f"Done! ({res['valid_articles']} articles, Score: {res['average_score']:.4f})")
            else:
                print("Failed (No articles)")
                
    # Save results
    with open('bulk_test_results.json', 'w') as f:
        json.dump(results, f, indent=4)
    print("\n[*] Bulk test complete! Results saved to bulk_test_results.json")

if __name__ == "__main__":
    main()
