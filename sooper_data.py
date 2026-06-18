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
import os
import matplotlib.pyplot as plt

# %% Function to fetch JSON with retries and backoff


def fetch_json(url, timeout=15, retries=3, backoff=1.5):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            print(f"HTTP {r.status_code} -> {url}")
        except Exception as e:
            print(f"Request failed (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            sleep_time = backoff ** attempt
            print(f"Retrying in {sleep_time:.1f} seconds...")
            time.sleep(sleep_time)

    print(f"Failed to fetch after {retries} attempts -> {url}")
    return None


# %%  Variables
start_date = '2026-05-06'
end_date = '2026-05-08'
# site_triplet = '626:UT:SNTL'   # Midway Valley
site_triplet = '1300:UT:SNTL'    # Powder Mountain
# site_triplet = '828:UT:SNTL'    # Trial Lake
# site_triplet = '518:CA:SNTL'    # Heavenly Valley

interval = 'HOURLY'
# interval = 'DAILY'

returnFlags = 'true'
returnOriginalValues = 'true'
returnSuspectData = 'true'

# list of elements that you want to request
# TOBS::2 - HMP500 1 hour average
# TOBS::1 - ST300 1 hour sample
# RHUMV::1 - 1 hour sample   ... may need to switch to 1-hr weighted average
# PTEMP:* 1 hour sample
# WTEQ::1 - 1 hour sample
# PREC::1 - 1 hour sample
# SNWD:: - USH9 1 hour sample
# WSPDV::1 - 1 hour average
# Solar - 1 hour average

elements = 'LWINV::1, LWOTV::1, SWINV::1, SWOTV::1, WSPDV::1, TOBS::2, RHUMV::1,  PTEMP:*, SNWD::1, WTEQ::1'


def build_df_dict():
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

    if json_data is None:
        print('Warning: Failed to fetch data from API. Using empty df_dict.')
        return {}

    data = json_data[0]['data']
    df_dict = {}

    for item in data:

        # Build dictionary element key
        elem = item['stationElement']['elementCode']

        # Build a unique key for each PTEMP sensor depth, but only one key for all other sensors.
        if elem == 'PTEMP':
            hd = item['stationElement']['heightDepth']
            dict_key = f'{elem}_{hd}'
        elif elem != 'PTEMP':
            dict_key = elem
        else:
            continue

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

    return df_dict


if __name__ == '__main__':

    # df_dict = build_df_dict()
    # try:
    #     create_layered_html_plot(df_dict)
    # except Exception as e:
    #     print('Error creating layered HTML plot:', e)

    try:
        df_dict = build_df_dict()
        print(
            f"df_dict built with {len(df_dict)} series: {list(df_dict.keys())}")
    except Exception as e:
        print("Error building df_dict:", e)
