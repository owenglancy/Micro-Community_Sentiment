import pandas as pd
import json
import numpy as np

with open("exports\\1565726185059778710.json") as f:
    data = json.load(f)
    df = pd.json_normalize(data)
    print(df)
    df.to_csv("exports\\testframe.csv", index=False)