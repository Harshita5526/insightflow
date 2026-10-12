import os
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

result = client.datasets.upload_file("sample_1500.csv", name="insightflow-sample-1500")
print(result)
