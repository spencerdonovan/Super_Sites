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

# %% Import sooper_data functions

from sooper_data import fetch_json
from sooper_data import build_df_dict
from sooper_data import surf_temp

# %% Define variables for data

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

elements = 'LWINV::1, LWOTV::1, SWINV::1, SWOTV::1, WSPDV::1, TOBS::2, RHUMV::1, PTEMP:*, SNWD::1, WTEQ::1'

# %%
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


# %% get top layer buried PTEMP data and add to dictionary
PTEMP = surf_temp(df_dict)

# Add DF to main dictionary
df_dict['PTEMP'] = PTEMP


print(
    f"df_dict built with {len(df_dict)} series: {list(df_dict.keys())}")

# %% Calculate actual vapor pressure see PDF from NWS

# "v" for edited value and "o" for raw data
TOBS_v = df_dict['TOBS']['value']
TOBS_o = df_dict['TOBS']['origValue']
RHUMV_v = df_dict['RHUMV']['value']
RHUMV_o = df_dict['RHUMV']['origValue']

# Convert TOBS from F to C
TOBS_v = (TOBS_v - 32) * 5/9
TOBS_o = (TOBS_o - 32) * 5/9


# Compute saturated vapor pressure [mb]
# the constant represents the saturation vapor pressure of water at the freezing point (0°C), which is exactly 6.11 mb
# 1 mbar = 1 hPa = 100 Pa, Pa = N/m^2 and N = kg * m / s^2
e_s_v = 6.11 * 10**((7.5 * TOBS_v)/(273.3 + TOBS_v))
e_s_o = 6.11 * 10**((7.5 * TOBS_o)/(273.3 + TOBS_o))

# Compute the actual vapor pressure using relative humidity [mb]
e_a_v = RHUMV_v/100 * e_s_v
e_a_o = RHUMV_o/100 * e_s_o

# Create actual vapor pressure dataframe
AVAP = df_dict['TOBS'][['date', 'value', 'origValue']].copy()
AVAP['value'] = e_a_v
AVAP['origValue'] = e_a_o

# Add dataframe to df_dict
df_dict['AVAP'] = AVAP
