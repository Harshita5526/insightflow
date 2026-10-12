import os
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

result = client.datasets.upload_file("feedback.csv", name="insightflow-feedback")
print(result)
