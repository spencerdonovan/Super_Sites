# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 14:00:31 2024

@author: Spencer.Donovan

Until the API is able to in extra ordinal data, this script uses csv exports from DMP to compare collocated temperature data
"""

# %% IMPORTS
import matplotlib.pyplot as plt
import itertools as it
import re
import io
import requests
import pandas as pd
import json
import datetime
from pathlib import Path


# Path to your folder
folder = Path(r"C:\USDA\Work\Github\Air_Temp_Drift_Check\tobs_export")

# Dictionary to hold raw CSV text
csv_files = {}

# Loop through all .csv files
for csv_file in folder.glob("*.csv"):
    key = csv_file.stem  # filename without extension

    with open(csv_file, "r", encoding="utf-8") as f:
        text = f.read()   # read entire file as raw text

    csv_files[key] = text

# csv_files["329-Beaver_Dams"].splitlines()[0]     # Header row in .csv


dfs = {}

for key, text in csv_files.items():

    # skip files that are empty text
    if not text.strip():
        print(f"{key}: empty, skipping")
        continue

    f = io.StringIO(text)

    try:
        df = pd.read_csv(
            f,
            engine="python",        # handles weird columns
            on_bad_lines="skip"     # skip problematic lines
        )
    except Exception as e:
        print(f"{key}: could not read ({e})")
        continue

    # files that parse but have no columns (just commas)…
    if df.shape[1] == 0:
        print(f"{key}: no usable columns, skipping")
        continue

    dfs[key] = df

print("Loaded:", list(dfs.keys()))


# %%
