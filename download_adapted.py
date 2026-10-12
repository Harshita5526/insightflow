import os
import pandas as pd
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

resp = client.datasets.download(
    "40b82b47-4f93-4666-8c70-344b6cb964dd",
    file_format="csv",
)

try:
    resp.write_to_file("adapted.csv")
except Exception:
    with open("adapted.csv", "wb") as f:
        f.write(resp.read())

df = pd.read_csv("adapted.csv")
print("rows:", len(df))
print("columns:", df.columns.tolist())
print(df.head(3).to_string())