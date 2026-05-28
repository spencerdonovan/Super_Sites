# -*- coding: utf-8 -*-
"""
Created on Fri May  8 14:00:31 2026

@author: Spencer.Donovan
"""

# %%
import requests
import pandas as pd
import json
import datetime
import time
import matplotlib.pyplot as plt

# %% Function to fetch JSON with retries and backoff


def fetch_json(url, timeout=15, retries=3, backoff=1.5):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            print(f"HTTP {r.status_code} → {url}")
        except Exception as e:
            print(f"Request failed (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            sleep_time = backoff ** attempt
            print(f"Retrying in {sleep_time:.1f} seconds...")
            time.sleep(sleep_time)

    print(f"Failed to fetch after {retries} attempts → {url}")
    return None


# %%  Variables
start_date = '2026-05-01'
end_date = '2026-05-08'
# site_triplet = '626:UT:SNTL'   # Midway Valley
site_triplet = '1300:UT:SNTL'    # Powder Mountain
# site_triplet = '828:UT:SNTL'    # Trial Lake

interval = 'HOURLY'
# interval = 'DAILY'

returnFlags = 'true'
returnOriginalValues = 'true'
returnSuspectData = 'true'

# list of elements that you want to request
elements = 'PTEMP:*, SNWD::1'


# %% API call using variables from above and formatting into json

url = f'https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?stationTriplets={site_triplet}&elements={elements}&duration={interval}&beginDate={start_date}&endDate={end_date}&periodRef=END&centralTendencyType=NONE&returnFlags={returnFlags}&returnOriginalValues={returnOriginalValues}&returnSuspectData={returnSuspectData}'

json_data = fetch_json(url)

# n = 0
# json_data[0]['data'][n]['stationElement']['elementCode']

# json_data[0]['data'][n]['stationElement']['heightDepth']

# json_data[0]['data'][0]['values']['date']
# json_data[0]['data'][n]['values']['value']
# json_data[0]['data'][n]['values']['origValue']
# json_data[0]['data'][n]['values']['qaflag']
# json_data[0]['data'][n]['values']['qcflag']


# %% Build dataframe from all elements PTEMP height as dictionary labels

data = json_data[0]['data']

df_dict = {}   # final dictionary of dataframes

for item in data:

    # Build dictionary element key
    elem = item['stationElement']['elementCode']

    # Seperate between SD and PTEMP labels
    if item['stationElement']['elementCode'] == 'PTEMP':
        hd = item['stationElement']['heightDepth']
        dict_key = f"{elem}_{hd}"
    if item['stationElement']['elementCode'] == 'SNWD':
        dict_key = f"{elem}"

    # Extract values array
    values = item['values']

    # Build dataframe from values area for elements
    df = pd.DataFrame({
        "date": [v["date"] for v in values] if "date" in values[0] else None,
        "value": [v["value"] for v in values],
        "origValue": [v["origValue"] for v in values],
        "qaFlag": [v["qaFlag"] for v in values],
        "qcFlag": [v["qcFlag"] for v in values]
    })

    # Store dataframe in dictionary
    df_dict[dict_key] = df

# %% Determine if Temperature bead is underneath snow or not

# for key, df in df_dict.items():
