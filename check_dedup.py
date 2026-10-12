import pandas as pd

raw = pd.read_csv("sample_1500.csv")
ad = pd.read_csv("adapted.csv")

print("raw rows:", len(raw))
print("raw unique reviews:", raw["review"].nunique())
print("adapted rows:", len(ad))
print("adapted reviews found in raw:", ad["review"].isin(raw["review"]).sum())
print(raw["review"].value_counts().head(5))