import os
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

dataset = client.datasets.get("40b82b47-4f93-4666-8c70-344b6cb964dd")
print("status:", dataset.status)
print("progress:", dataset.progress)
print("run_id:", dataset.run_id)
print("error:", dataset.error_data)
print("evaluation:", dataset.evaluation_summary)