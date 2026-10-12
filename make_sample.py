import pandas as pd

df = pd.read_csv("feedback.csv")
sample = df.sample(n=1500, random_state=42)
sample.to_csv("sample_1500.csv", index=False)
print(len(sample), "rows saved")
print(sample["category"].value_counts())
