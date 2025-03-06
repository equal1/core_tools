import json
import requests
from pprint import pprint


base = "http://127.0.0.1:8001"

# %%
r = requests.get(base + "/functions")
print(r.status_code)
pprint(json.loads(r.content))


# %%

r = requests.post(base + "/run",
                  data={
                      "__name__": "sayHi",
                      "name": "Oriol",
                      "times": 2,
                      })
print(r.status_code)
pprint(json.loads(r.content))

r = requests.post(base + "/run",
                  data={
                      "__name__": "Fit it",
                      "x": 13.0,
                      "mode": "RIGHT",
                      })
print(r.status_code)
pprint(json.loads(r.content))
