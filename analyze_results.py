import json
import statistics

with open('bulk_test_results.json', 'r') as f:
    data = json.load(f)

scores = [item['average_score'] for item in data]
valid = [item for item in data if item['valid_articles'] > 0]

print(f"Total Instruments: {len(data)}")
print(f"Mean Score: {statistics.mean(scores):.4f}")
print(f"Median Score: {statistics.median(scores):.4f}")
print(f"Max Score: {max(scores):.4f} ({data[scores.index(max(scores))]['ticker']})")
print(f"Min Score: {min(scores):.4f} ({data[scores.index(min(scores))]['ticker']})")

# Percentiles
sorted_scores = sorted(scores)
p10 = sorted_scores[int(len(scores)*0.1)]
p25 = sorted_scores[int(len(scores)*0.25)]
p75 = sorted_scores[int(len(scores)*0.75)]
p90 = sorted_scores[int(len(scores)*0.90)]

print(f"10th Percentile: {p10:.4f}")
print(f"25th Percentile: {p25:.4f}")
print(f"75th Percentile: {p75:.4f}")
print(f"90th Percentile: {p90:.4f}")

# Threshold count with current 0.25 threshold
buys = sum(1 for s in scores if s >= 0.25)
sells = sum(1 for s in scores if s <= -0.25)
holds = sum(1 for s in scores if -0.25 < s < 0.25)

print(f"\nCurrent Logic (Threshold 0.25):")
print(f"BUYs: {buys}, SELLs: {sells}, HOLDs: {holds}")

# Let's see what happens if threshold is 0.05
buys_05 = sum(1 for s in scores if s >= 0.05)
sells_05 = sum(1 for s in scores if s <= -0.05)
holds_05 = sum(1 for s in scores if -0.05 < s < 0.05)

print(f"\nProposed Logic (Threshold 0.05):")
print(f"BUYs: {buys_05}, SELLs: {sells_05}, HOLDs: {holds_05}")

# Alternative: Ratio-based logic
def get_ratio_decision(item):
    pos = item['positive']
    neg = item['negative']
    if pos == 0 and neg == 0: return "HOLD"
    # if positive articles are 50% more than negative
    if pos > neg * 1.5: return "BUY"
    if neg > pos * 1.5: return "SELL"
    return "HOLD"

r_buys = sum(1 for item in data if get_ratio_decision(item) == "BUY")
r_sells = sum(1 for item in data if get_ratio_decision(item) == "SELL")
r_holds = sum(1 for item in data if get_ratio_decision(item) == "HOLD")

print(f"\nRatio Logic (Pos > 1.5*Neg):")
print(f"BUYs: {r_buys}, SELLs: {r_sells}, HOLDs: {r_holds}")
