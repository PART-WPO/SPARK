#!/usr/bin/env python3
import pandas as pd
import json

# 1. load your CSV from GitHub
csv_url = "https://raw.githubusercontent.com/PART-WPO/SPARK/main/SPARK%20Report%20-%20SPARK%20Report.csv"
df = pd.read_csv(csv_url)

# 2. build a dict mapping each output‑URL → how many results
counts = {}
for cell in df["REACH URLs"].fillna("").str.split(/\s*;\s*/):
    for url in cell:
        if not url: 
            continue
        counts[url] = counts.get(url, 0) + 1

# 3. write it out
with open("counts.json", "w") as f:
    json.dump(counts, f, indent=2)
