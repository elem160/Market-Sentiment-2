import sys
import os
import yfinance as yf
import feedparser
import urllib.parse
from transformers import pipeline
from dotenv import load_dotenv
from openai import OpenAI
from googlenewsdecoder import gnewsdecoder
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

load_dotenv()
openrouter_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key) if openrouter_key else None
MODEL_ID = "nvidia/nemotron-3-ultra-550b-a55b:free"

def batch_verify_catalysts(headlines):
    if not client or not headlines:
        # Fallback if no API key: assume all are catalysts
        return list(range(1, len(headlines) + 1))
        
    prompt = ""
    for i, h in enumerate(headlines):
        prompt += f"{i+1}. {h}\n"
        
    try:
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": "You are a financial expert filtering noise. Given the following numbered list of headlines, identify ONLY the ones that are true market-moving catalysts (e.g., earnings beat/miss, major M&A, regulatory changes, material product news, macroeconomic data). Ignore opinion, speculation, clickbait, and routine noise. Reply ONLY with a comma-separated list of the numbers corresponding to the catalysts. For example: 1, 4, 15. If absolutely NONE are catalysts, reply with NONE. Do not provide any other text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        if content.upper() == "NONE":
            return []
            
        # Parse the comma separated numbers
        catalyst_indices = []
        for num_str in content.replace('\n', ',').split(','):
            num_str = num_str.strip()
            if num_str.isdigit():
                catalyst_indices.append(int(num_str))
        return catalyst_indices
    except Exception as e:
        print(f"  [!] Error calling OpenRouter: {e}")
        return list(range(1, len(headlines) + 1))

def format_yf_ticker(ticker):
    if "/" in ticker:
        parts = ticker.split("/")
        return f"{parts[0]}{parts[1]}=X"
    return ticker

def get_yahoo_finance_news(ticker):
    yf_ticker = format_yf_ticker(ticker)
    print(f"[*] Fetching Yahoo Finance news for {yf_ticker} ({ticker})...")
    try:
        stock = yf.Ticker(yf_ticker)
        news_items = stock.news
        results = []
        
        if not isinstance(news_items, list):
            print(f"[!] Yahoo Finance returned no valid news format for {yf_ticker}.")
            return []
            
        # Get all available recent articles
        for item in news_items:
            if not isinstance(item, dict):
                continue
                
            if 'content' in item and 'title' in item['content']:
                title = item['content']['title']
            else:
                title = item.get("title", "")
                
            publisher = item.get("provider", {}).get("displayName", "")
            if not publisher:
                publisher = item.get("publisher", "")
                
            link = item.get("content", {}).get("clickThroughUrl", {}).get("url", "")
            if not link:
                link = item.get("link", "")
                
            summary = item.get("content", {}).get("summary", "") or item.get("summary", "") or item.get("content", {}).get("description", "")
            results.append({"text": f"{title}", "summary": summary, "source": f"Yahoo - {publisher}", "link": link})
        return results
    except Exception as e:
        print(f"[!] Error fetching Yahoo news: {e}")
        return []

def get_google_rss_news(ticker, source_name):
    print(f"[*] Fetching {source_name} news via Google News RSS for {ticker}...")
    try:
        query = f"{ticker} {source_name}"
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(url)
        results = []
        for entry in feed.entries[:50]:
            title = entry.title
            link = entry.link
            summary = entry.get("summary", "")
            results.append({"text": title, "summary": summary, "source": f"{source_name} (RSS)", "link": link})
        return results
    except Exception as e:
        print(f"[!] Error fetching {source_name} news: {e}")
        return []

def get_direct_forex_rss(name, rss_url):
    print(f"[*] Fetching direct Forex RSS from {name}...")
    try:
        feed = feedparser.parse(rss_url)
        results = []
        for entry in feed.entries[:30]:
            title = entry.title
            link = entry.link
            summary = entry.get("summary", "") or entry.get("description", "")
            results.append({"text": title, "summary": summary, "source": name, "link": link})
        return results
    except Exception as e:
        print(f"[!] Error fetching {name} RSS: {e}")
        return []

def fetch_single_lead(item):
    title = item["text"]
    summary = item.get("summary", "")
    link = item.get("link", "")
    source = item["source"]
    
    fallback_text = f"{title}. {summary}".strip()
    if len(fallback_text.split()) > 300:
        fallback_text = " ".join(fallback_text.split()[:300])[:1400]
        
    if not link:
        item["lead_text"] = fallback_text
        return item
        
    # Skip web scraping for known Cloudflare / paywalled publishers to save time and prevent 401/403 blocks
    if any(blocked in source for blocked in ["Reuters", "Bloomberg", "Wall Street Journal", "MarketWatch"]):
        item["lead_text"] = fallback_text
        return item
        
    try:
        target_url = link
        if "news.google.com" in link:
            res = gnewsdecoder(link, interval=0.01)
            if res.get("status"):
                target_url = res["decoded_url"]
                
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        r = requests.get(target_url, headers=headers, timeout=3)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            paragraphs = [p.get_text().strip() for p in soup.find_all('p') if len(p.get_text().strip()) > 30]
            if len(paragraphs) >= 2:
                full_body = " ".join(paragraphs)
                lead_words = full_body.split()[:300]
                item["lead_text"] = (f"{title}. " + " ".join(lead_words))[:1400]
                return item
    except Exception:
        pass
        
    item["lead_text"] = fallback_text
    return item

def enrich_with_lead_text(news_items):
    print(f"\n[*] Extracting Inverted Pyramid Lead text (first ~400 words) for {len(news_items)} articles using 20 parallel threads...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        enriched = list(executor.map(fetch_single_lead, news_items))
    print("[+] Lead extraction complete.\n")
    return enriched

def analyze_with_finbert(ticker, news_items):
    print("[*] Loading local FinBERT NLP model (ProsusAI/finbert)...")
    try:
        # Load the FinBERT model pipeline for sentiment analysis
        sentiment_pipeline = pipeline("sentiment-analysis", model="ProsusAI/finbert")
    except Exception as e:
        print(f"[!] Error loading FinBERT model: {e}")
        return

    # Option 3: Extract Inverted Pyramid Lead (first ~400 words of article body / summary)
    news_items = enrich_with_lead_text(news_items)

    print("[*] Analyzing sentiment of Inverted Pyramid Lead texts...\n")
    
    total_score = 0.0
    valid_articles = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0

    print("=== INDIVIDUAL ARTICLE LEAD SENTIMENT ===")
    
    candidates = []
    
    for item in news_items:
        # Use extracted lead text (first ~400 words of article body / summary)
        text = item.get("lead_text", item["text"])
        # Take first 300 words and max 1400 characters to ensure it fits cleanly within FinBERT's 512 token window
        words = text.split()[:300]
        truncated_text = " ".join(words)[:1400]
        try:
            result = sentiment_pipeline(truncated_text)[0]
            label = result['label']
            score = result['score']
            
            # Print individual result safely (show preview of text analyzed)
            safe_preview = truncated_text[:120].encode('ascii', 'ignore').decode('ascii') + "..."
            print(f"- [{item['source']}] {safe_preview}")
            print(f"  FinBERT Sentiment: {label.upper()} (Confidence: {score:.2f})")
            
            if label in ['positive', 'negative']:
                candidates.append({
                    'text': safe_text,
                    'label': label,
                    'score': score
                })
                print("  Status: Added to LLM Verification Batch\n")
            else:
                neutral_count += 1
                print("  Status: Ignored (Neutral)\n")
            
            valid_articles += 1
        except Exception as e:
            safe_text = text.encode('ascii', 'ignore').decode('ascii')
            print(f"[!] Could not analyze text: {safe_text} - Error: {e}")
            
    print("=====================================\n")

    if valid_articles == 0:
        print("[!] No valid articles to score.")
        return

    # Batch verification
    print(f"[*] Sending {len(candidates)} potential catalysts to Nemotron for batch verification...")
    headlines_only = [c['text'] for c in candidates]
    verified_indices = batch_verify_catalysts(headlines_only)
    
    print(f"[*] Nemotron verified {len(verified_indices)} actual catalysts.")
    
    # Process results
    for i, candidate in enumerate(candidates):
        # 1-based indexing from the LLM prompt
        is_catalyst = (i + 1) in verified_indices
        if is_catalyst:
            if candidate['label'] == 'positive':
                total_score += candidate['score']
                positive_count += 1
            else:
                total_score -= candidate['score']
                negative_count += 1
        else:
            neutral_count += 1

    # Calculate average score (-1 to 1)
    average_score = total_score / valid_articles
    
    # Decision threshold logic (Ratio-based to avoid neutral dilution)
    if positive_count == 0 and negative_count == 0:
        decision = "HOLD"
    elif positive_count > (negative_count * 1.5):
        decision = "BUY"
    elif negative_count > (positive_count * 1.5):
        decision = "SELL"
    else:
        decision = "HOLD"
        
    print("=== AI ANALYSIS RESULT (HYBRID FINBERT + NEMOTRON) ===")
    print(f"DECISION: {decision}")
    print(f"AGGREGATED SCORE: {average_score:.4f} (Scale: -1.0 to 1.0)")
    print(f"SENTIMENT BREAKDOWN: {positive_count} Positive | {negative_count} Negative | {neutral_count} Neutral")
    print(f"RATIONALE: Analyzed {valid_articles} recent headlines. FinBERT flagged potential sentiment, and Nemotron filtered out the noise. "
          f"Based on the ratio of VERIFIED positive to negative catalysts, the sentiment mathematically tilted towards '{decision}'.")
    print("========================================================\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python simple_scraper.py <TICKER>")
        sys.exit(1)
        
    ticker = sys.argv[1].upper()
    
    all_news = []
    
    # Fetch from Yahoo Finance
    all_news.extend(get_yahoo_finance_news(ticker))
    
    # If forex pair or currency, also fetch from specialized Forex RSS feeds
    if "/" in ticker or "USD" in ticker or "EUR" in ticker or "JPY" in ticker or "GBP" in ticker:
        all_news.extend(get_direct_forex_rss("Investing.com Forex", "https://www.investing.com/rss/news_1.rss"))
        all_news.extend(get_direct_forex_rss("FXStreet", "https://www.fxstreet.com/rss/news"))
        yf_ticker = format_yf_ticker(ticker)
        all_news.extend(get_direct_forex_rss("Yahoo Finance RSS", f"https://finance.yahoo.com/rss/headline?s={yf_ticker}"))
    
    # Fetch from top financial sources via Google News RSS
    sources = ["Reuters", "Bloomberg", "CNBC", "Wall Street Journal", "MarketWatch", "Seeking Alpha", "Motley Fool"]
    for source in sources:
        all_news.extend(get_google_rss_news(ticker, source))
    
    if not all_news:
        print(f"[!] Could not find any recent news for {ticker}.")
        sys.exit(1)
        
    # Analyze
    analyze_with_finbert(ticker, all_news)

if __name__ == "__main__":
    main()
