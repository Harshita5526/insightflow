import os
from dotenv import load_dotenv
from adaption import Adaption

load_dotenv()
client = Adaption(api_key=os.environ["ADAPTION_API_KEY"])

run = client.datasets.run(
    "40b82b47-4f93-4666-8c70-344b6cb964dd",
    column_mapping={"prompt": "review", "completion": "category"},
    recipe_specification={"recipes": {"deduplication": True}},
    estimate=True,
)
print(run)