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
import numpy as np
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


# %% Function that uses fetch_json to get data for a site

def build_df_dict(site_triplet: str, elements: str, interval: str, start_date: str, end_date: str, returnFlags: str, returnOriginalValues: str, returnSuspectData: str):

    # def build_df_dict():
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


# %% GET PTEMP DATA FROM BEAD NEAREST SNOW SURFACE

# PTEMP heights in inches are 126, 118, 110, 102, 94, 87, 79, 71, 63, 55, 47, 39, 31, 24, 16, 8, 0, -8
# Logic to determine which PTEMP sensor depth to use for snow surface temperature based on the SNWD value.  If SNWD matches PTEMP height use that PTEMP, e.g. if SNWD is 63 use PTEMP 63.  If SNWD is between two sensor depths, use the sensor depth that is closest but less than the SNWD value. e.g if SNWD is 40 use PTEMP_39, if SNWD is 20 use PTEMP_16. If SNWD is less than -8 or if SNWD is greater than 126 code should not run.


# snwd = df_dict['SNWD']['value']

### NEED ---- to add filter for fluctuating snwd values and outlier values ######

def surf_temp(dictionary: dict):
    """
    Build a new DataFrame representing snow-surface PTEMP values by selecting,
    for each SNWD row, the PTEMP sensor that is closest but not greater than SNWD.

    Parameters
    ----------
    dictionary : dict
        A dict whose keys include:
          - 'SNWD': a DataFrame with at least a 'value' column (Series of snow depth)
          - 'PTEMP_{h}': DataFrames for each sensor height h with columns:
                'date', 'value', 'origValue', 'qaFlag', 'qcFlag'

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: 'date', 'value', 'origValue', 'qaFlag', 'qcFlag',
        one row per SNWD row, taken from the appropriate PTEMP_{h} dataframe.
    """

    snwd = dictionary['SNWD']['value']  # value is the edited value

    # Static PTEMP reference heights for loop calculation
    ptemp_heights = [126, 118, 110, 102, 94, 87, 79,
                     71, 63, 55, 47, 39, 31, 24, 16, 8, 0, -8]

    # Determine PTEMP height to use for each SNWD data point
    max_height = []
    for i in snwd:
        height = []
        # if snwd is invalid or outside of the height of the beaded stream temp cable
        if pd.isna(i) or i < 0 or i > 126:
            height.append(np.nan)
            continue
        # collect all sensor heights <= snwd and pick the max (closest from below)
        for h in ptemp_heights:
            if h <= i:
                height.append(h)
        max_height.append(max(height))

    # Get top (buried) PTEMP data according to max_height and create new dictionary for PTEMP data at snow surface temperature

    # Empty Dictionary setup
    PTEMP = {
        'date': [],
        'value': [],
        'origValue': [],
        'qaFlag': [],
        'qcFlag': [],
        'height': [],
    }

    # For row z in max_height, the selected PTEMP sensor is PTEMP_k. Pull the z‑th value (row number) from that sensor’s (PTEMP_k) dataframe and append it into the new PTEMP record.
    for z, k in enumerate(max_height):
        if pd.isna(k):
            PTEMP['date'].append(np.nan)
            PTEMP['value'].append(np.nan)
            PTEMP['origValue'].append(np.nan)
            PTEMP['qaFlag'].append(np.nan)
            PTEMP['qcFlag'].append(np.nan)
            PTEMP['height'].append(np.nan)
        else:
            key = f'PTEMP_{k}'
            if key in dictionary and z < len(dictionary[key]):
                source_row = dictionary[key].iloc[z]
                PTEMP['date'].append(source_row['date'])
                PTEMP['value'].append(source_row['value'])
                PTEMP['origValue'].append(source_row['origValue'])
                PTEMP['qaFlag'].append(source_row['qaFlag'])
                PTEMP['qcFlag'].append(source_row['qcFlag'])
                PTEMP['height'].append(k)
            else:
                PTEMP['date'].append(np.nan)
                PTEMP['value'].append(np.nan)
                PTEMP['origValue'].append(np.nan)
                PTEMP['qaFlag'].append(np.nan)
                PTEMP['qcFlag'].append(np.nan)
                PTEMP['height'].append(np.nan)

    # Convert dictionary to DF
    PTEMP = pd.DataFrame(PTEMP)
    return PTEMP

# %% Testing PTEMP heights

# PTEMP = surf_temp(df_dict)

# # Add DF to main dictionary
# df_dict['PTEMP'] = PTEMP


# %%
if __name__ == '__main__':

    # Variables for build_df_dict function

    start_date = '2026-01-01'
    end_date = '2026-02-01'
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
    # RHUMV::1 - 1 hour weighted average
    # PTEMP:* 1 hour sample
    # WTEQ::1 - 1 hour sample
    # PREC::1 - 1 hour sample
    # SNWD:: - USH9 1 hour sample
    # WSPDV::1 - 1 hour average
    # Solar - 1 hour average

    elements = 'LWINV::1, LWOTV::1, SWINV::1, SWOTV::1, WSPDV::1, TOBS::2, RHUMV::1,  PTEMP:*, SNWD::1, WTEQ::1'

    df_dict = build_df_dict(
        site_triplet,
        elements,
        interval,
        start_date,
        end_date,
        returnFlags,
        returnOriginalValues,   # match the parameter name exactly
        returnSuspectData,
    )

    # PTEMP = surf_temp(df_dict)

    # # Add DF to main dictionary
    # df_dict['PTEMP'] = PTEMP

    try:
        df_dict = build_df_dict(site_triplet, elements, interval, start_date,
                                end_date, returnFlags, returnOriginalValues, returnSuspectData)

        PTEMP = surf_temp(df_dict)
        df_dict['PTEMP'] = PTEMP

        print(
            f"df_dict built with {len(df_dict)} series: {list(df_dict.keys())}")

    except Exception as e:
        print("Error building df_dict:", e)

# %%
