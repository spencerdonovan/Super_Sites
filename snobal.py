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
es_v = 6.11 * 10**((7.5 * TOBS_v)/(273.3 + TOBS_v))
es_o = 6.11 * 10**((7.5 * TOBS_o)/(273.3 + TOBS_o))

# Compute the actual vapor pressure using relative humidity [mb]
ea_v = RHUMV_v/100 * es_v
ea_o = RHUMV_o/100 * es_o

# Create actual vapor pressure dataframe
AVAP = df_dict['TOBS'][['date', 'value', 'origValue']].copy()
AVAP['value'] = ea_v
AVAP['origValue'] = ea_o

# Add dataframe to df_dict
df_dict['AVAP'] = AVAP

# %% Calculate air density P_a

# p is Pa for the the station elevation (1300) Powder Mountain = 8490, (828) Trial Lake = 9970, (626) Midway Valley = 9830, (518) Heavenly Valley = 8540

# site_triplet = '626:UT:SNTL'   # Midway Valley
site_triplet = '1300:UT:SNTL'    # Powder Mountain
# site_triplet = '828:UT:SNTL'    # Trial Lake
# site_triplet = '518:CA:SNTL'    # Heavenly Valley

if site_triplet == '626:UT:SNTL' or site_triplet == '828:UT:SNTL':
    p = 69800
elif site_triplet == '1300:UT:SNTL' or site_triple == '518:CA:SNTL':
    p = 72500

Rd = 287  # [J kg^-1 K^-1] represents the specific gas constant for dry air

# Air Density [kg m^-1]
rhoair_v = p / (Rd * (TOBS_v+273))
rhoair_o = p / (Rd * (TOBS_o+273))

# Create air density dataframe
rhoair = df_dict['AVAP'][['date', 'value', 'origValue']].copy()
rhoair['value'] = rhoair_v
rhoair['origValue'] = rhoair_o

# Add dataframe to df_dict
df_dict['rhoair'] = rhoair

# %% Calculate specific humidity Q_a
# 0.622 is the ratio of the physical weight of a water molecule compared to the average weight of a dry air molecule

# Air specific humidity
qa_v = 0.622 * (ea_v / (p - (1 - 0.622) * ea_v))
qa_o = 0.622 * (ea_o / (p - (1 - 0.622) * ea_o))

# Humidity gradient
