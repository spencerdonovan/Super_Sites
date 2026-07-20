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

elements = 'LWINV::1, LWOTV::1, SWINV::1, SWOTV::1, WSPDV::1, TOBS::2, RHUMV::1,  PTEMP:*, SNWD::1, WTEQ::1'

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
