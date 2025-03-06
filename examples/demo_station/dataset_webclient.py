import json
import requests
from pprint import pprint


base = "http://127.0.0.1:8002"


# %%

r = requests.get(base + "/latest",
                 params={
                     "start_time": "2025-03-06 15:30",
                     })
print(r.status_code)
pprint(json.loads(r.content))
