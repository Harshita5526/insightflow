import os
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

run = client.datasets.run(
    "2ba88a55-9b86-401e-a955-bc54c655d52c",
    column_mapping={"prompt": "review", "completion": "category"},
    recipe_specification={"recipes": {"deduplication": True}},
    estimate=True,
)
print(run)