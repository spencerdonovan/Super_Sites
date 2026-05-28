# -*- coding: utf-8 -*-
"""
Snow & Precipitation QC Dashboard

Created on Mon May  5 11:30:00 2025

@author: Spencer.Donovan
"""


# # %%
# # Using ARCcwr environment


# from flask import Flask, request, render_template_string
# import pandas as pd
# import requests
# from dmp_qc import check_qc_rules_all   # QC function


# # ********* Load region CSV ********
# df_regions = pd.read_csv("SiteList.csv")

# # ********** Create the Flask app **********

# # If you run the file directly, __name__ becomes "__main__".
# # If the file is imported as a module, __name__ becomes the module name.

# app = Flask(__name__)

# # ******** HTML template ************
# TEMPLATE = """
# <!doctype html>
# <html>
# <head>
#   <title>QC Dashboard</title>
#   <style>
#     body { font-family: Arial, sans-serif; margin: 40px; }
#     h1 { color: #2c3e50; }
#     table { border-collapse: collapse; width: 100%%; margin-bottom: 30px; }
#     th, td { border: 1px solid #ccc; padding: 6px; text-align: left; }
#     th { background-color: #f2f2f2; }
#   </style>
# </head>
# <body>
#   <h1>❄️ Snow, SWE, & Precipitation QC Dashboard</h1>

# <p style="margin-bottom:20px; font-style:italic; color:#003366;"> - Enter a site configuration or region name (e.g.    <code>UTDCO</code>, <code>UINTA</code>, <code>SEUT</code>), or full station triplets (e.g. <code>364:UT:SNTL</code>). <br><br> - Use commas or spaces to separate multiple entries.<br><br> - Start date and End date are in MM-DD-YYYY format, <br><br> - Choose either DAILY or HOURLY interval.<br><br> - The dashboard may need to be refreshed if your query fails. The dashboard may also fail if multiple users are running a query at the same time or your internet is experiencing a slowdown :( </p>

#   <form method="get">
#     Site config:<input type="text" name="site_config" value="{{ site_config }}"><br>
#     Start date: <input type="date" name="start" value="{{ start }}"><br>
#     End date: <input type="date" name="end" value="{{ end }}"><br>
#     Interval:
#     <select name="interval">
#       <option value="DAILY" {% if interval=="DAILY" %}selected{% endif %}>DAILY</option>
#       <option value="HOURLY" {% if interval=="HOURLY" %}selected{% endif %}>HOURLY</option>
#     </select><br><br>
#     <input type="submit" value="Run QC">
#   </form>

#   {% if results %}

#     {% if results["rule1"].empty and results["rule3"].empty and results["rule4"].empty %}
#     <h2 style="color:gold;">❄️❄️❄️ 😊 Huzzah! No QC rule violations were found 😊❄️❄️❄️</h2>
#     {% endif %}

#     <h2>Rule 1 Violations: No decreases in accumulated precipitation.</h2>
#     {{ results["rule1"].to_html(index=False) | safe }}

#     <h2>Rule 3 Violations: No increase in SWE without corresponding increase in precipitation.</h2>
#     {{ results["rule3"].to_html(index=False) | safe }}

#     <h2>Rule 4 Violations: No increase in snow depth without corresponding increase in SWE.</h2>
#     {{ results["rule4"].to_html(index=False) | safe }}

#     <h2>Rule Z Violations: Occurrences where ρ_<code>snow</code> = ∞.</h2>
#     {{ results["ruleZ"].to_html(index=False) | safe }}

#     <h2>Skipped Stations</h2>
#     {{ results["skipped"].to_html(index=False) | safe }}
#   {% endif %}
# </body>
# </html>
# """

# # ************ Define the route *************


# @app.route("/", methods=["GET"])
# def qc_dashboard():
#     site_config = request.args.get("site_config", "")
#     start = request.args.get("start", "")
#     end = request.args.get("end", "")
#     interval = request.args.get("interval", "")

#     results = None
#     selected_triplets = []

#     if site_config and start and end and interval:
#         # Normalize tokens: uppercase, strip underscores and dots
#         tokens = [t.strip()
#                   for t in site_config.replace(",", " ").split() if t.strip()]
#         tokens = [t.upper().replace("_", "").replace(".", "") for t in tokens]

#         # Case: UTDCO → all triplets from df_regions
#         if site_config.upper().replace("_", "").replace(".", "") == "UTDCO":
#             selected_triplets = df_regions["stationTriplet"].tolist()

#         # Case: explicit triplets (contain ":")
#         elif all(":" in t for t in tokens):
#             selected_triplets = df_regions.loc[
#                 df_regions["stationTriplet"].isin(tokens), "stationTriplet"
#             ].tolist()

#         # Case: region names (normalized)
#         elif all(t in df_regions["editingRegion"].str.upper().unique() for t in tokens):
#             selected_triplets = df_regions.loc[
#                 df_regions["editingRegion"].str.upper().isin(
#                     tokens), "stationTriplet"
#             ].tolist()

#         else:
#             selected_triplets = []

#         # --- Fetch data for each triplet ---
#         all_station_results = []
#         for site_triplet in selected_triplets:
#             site_triplet_encoded = site_triplet.replace(":", "%3A")
#             url = (
#                 f"https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?"
#                 f"stationTriplets={site_triplet_encoded}&elements=WTEQ,PREC,SNWD,SNDN&duration={interval}"
#                 f"&beginDate={start}&endDate={end}&periodRef=END"
#                 f"&centralTendencyType=NONE&returnFlags=false&returnOriginalValues=true&returnSuspectData=true"
#             )
#             api = requests.get(url)
#             if api.status_code == 200:
#                 data = api.json()
#                 if data:
#                     all_station_results.append(
#                         {"stationTriplet": site_triplet, "data": data}
#                     )
#             else:
#                 print(f"Error {api.status_code} for {site_triplet}")

#         # --- Run QC if we have results ---
#         if all_station_results:
#             results_all = check_qc_rules_all(all_station_results, df_regions)
#             results = results_all

#     # --- Render template ---
#     return render_template_string(
#         TEMPLATE,
#         site_config=site_config,
#         start=start,
#         end=end,
#         interval=interval,
#         results=results,
#     )


# # ************ Run the app **********
# if __name__ == "__main__":
#     app.run(debug=True, use_reloader=False)


# %%
# %%
# Using ARCcwr environment

from flask import Flask, request, render_template_string
import os
import pandas as pd
import requests
from dmp_qc import check_qc_rules_all   # QC function

# ********* Load region CSV ********
df_regions = pd.read_csv("SiteList.csv")

# Streamlit host can be overridden through environment on PythonAnywhere.
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501")

# --- Minimal normalization helper (new) ---


def _norm(s: str) -> str:
    """Uppercase + remove underscores, dots, and spaces."""
    return s.upper().replace("_", "").replace(".", "").replace(" ", "").strip()


# Build a normalized column for editingRegion (new)
df_regions_norm = df_regions.copy()
df_regions_norm["editingRegionNorm"] = df_regions_norm["editingRegion"].apply(
    _norm)

# --- Consistent table HTML helper (new) ---


def df_to_html(df: pd.DataFrame) -> str:
    """Render DataFrame tables with stable styling regardless of pandas/browser defaults."""
    return df.to_html(
        index=False,
        classes="qc-table",
        na_rep="",
        border=0,
        justify="left",
        escape=False,  # keep HTML in headers/labels if present
    )


# ********** Create the Flask app **********
app = Flask(__name__)

# ******** HTML template ************
TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>QC Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; }
    h1 { color: #2c3e50; }

    /* Simple tab navigation */
    .tabs { margin-bottom: 16px; }
    .tabs a { padding: 8px 14px; margin-right: 8px; text-decoration: none; border: 1px solid #d0d7e6; background:#f7f9fc; color:#003366; border-radius:4px; }
    .tabs a.active { background:#2c7be5; color:white; }

    /* Don't force 100% width; let tables size to content */
    table { border-collapse: collapse; margin-bottom: 30px; }

    /* Base cell styles */
    th, td { border: 1px solid #ccc; padding: 4px; text-align: left; }
    th { background-color: #f2f2f2; }

    .qc-table { width: auto !important; table-layout: auto; font-size: 14px; margin-bottom: 30px; }
    .qc-table th, .qc-table td { border: 1px solid #ccc; padding: 4px; text-align: left; white-space: nowrap; }
    .table-wrap { overflow-x: auto; max-width: 100%; }
    .banner { background: #f7fafc; border: 1px solid #dbe5f3; padding: 10px; margin: 16px 0; }
    .empty { color: #888; font-style: italic; }
  </style>
</head>
<body>
  <h1>❄️ Snow, SWE, & Precipitation QC Dashboard</h1>

  <div class="tabs">
    <a href="/?view=qc" class="{% if view!='streamlit' %}active{% endif %}">QC Dashboard</a>
<a href="/?view=streamlit" class="{% if view=='streamlit' %}active{% endif %}">Profile Temperature Dashboard</a>
  </div>
  
  {% if view == 'streamlit' %}
    <div class="banner">
      <p>The Profile Temperature Dashboard runs as a separate Streamlit app. Click the button below to open it in a new tab.</p>
      <p><a href="{{ streamlit_url }}" target="_blank" style="display:inline-block;padding:10px 14px;background:#2c7be5;color:white;text-decoration:none;border-radius:4px;">Open Streamlit dashboard</a></p>
      <p style="font-size:13px;color:#666;">If the Streamlit server is not running, start it with: <code>python -m streamlit run streamlit_app.py</code></p>
    </div>
  {% else %}

  <p style="margin-bottom:20px; font-style:italic; color:#003366;">
    - Enter a site configuration or region name (e.g. <code>UTDCO</code>, <code>UINTA</code>, <code>SEUT</code>), or full station triplets (e.g. <code>364:UT:SNTL</code>).
    <br><br>
    - Use commas or spaces to separate multiple entries.
    <br><br>
    - Start date and End date are in MM-DD-YYYY format,
    <br><br>
    - Choose either DAILY or HOURLY interval.
    <br><br>
    - The dashboard may need to be refreshed if your query fails. The dashboard may also fail if multiple users are running a query at the same time or your internet is experiencing a slowdown :(
  </p>

    <form method="get">
      <input type="hidden" name="view" value="qc">
      Site config: <input type="text" name="site_config" value="{{ site_config }}"><br>
      Start date:  <input type="date" name="start" value="{{ start }}"><br>
      End date:    <input type="date" name="end" value="{{ end }}"><br>
      Interval:
      <select name="interval">
        <option value="DAILY"  {% if interval=="DAILY"  %}selected{% endif %}>DAILY</option>
        <option value="HOURLY" {% if interval=="HOURLY" %}selected{% endif %}>HOURLY</option>
      </select><br><br>
      <input type="submit" value="Run QC">
    </form>

    {% if selection_info %}
    <div class="banner">
      <b>Selected Stations</b><br>
      Count: <b>{{ selection_info.count }}</b><br>
      Sample: {% if selection_info.sample and selection_info.sample|length > 0 %}
                {{ selection_info.sample|join(', ') }}
              {% else %}
                <span class="empty">none</span>
              {% endif %}
    </div>
    {% endif %}

    {% if results %}

      {% if results["rule1"].empty and results["rule3"].empty and results["rule4"].empty and results["ruleZ"].empty %}
      <h2 style="color:gold;">❄️❄️❄️ 😊 Huzzah! No QC rule violations were found 😊❄️❄️❄️</h2>
      {% endif %}

      <h2>Rule 1 Violations: No decreases in accumulated precipitation.</h2>
      <div class="table-wrap">{{ rule1_html | safe }}</div>

      <h2>Rule 3 Violations: No increase in SWE without corresponding increase in precipitation.</h2>
      <div class="table-wrap">{{ rule3_html | safe }}</div>

      <h2>Rule 4 Violations: No increase in snow depth without corresponding increase in SWE.</h2>
      <div class="table-wrap">{{ rule4_html | safe }}</div>

      <h2>Rule Z Violations: Occurrences where ρ_<code>snow</code> = ∞.</h2>
      <div class="table-wrap">{{ ruleZ_html | safe }}</div>

      <h2>Skipped Stations</h2>
      <div class="table-wrap">{{ skipped_html | safe }}</div>
    {% endif %}

  {% endif %}
</body>
</html>
"""

# ************ Define the route *************


@app.route("/", methods=["GET"])
def qc_dashboard():
    site_config = request.args.get("site_config", "")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    interval = request.args.get("interval", "")
    view = request.args.get("view", "qc")

    results = None
    selected_triplets = []
    selection_info = {"count": 0, "sample": []}

    # Defaults for table HTML if we don't have results yet
    rule1_html = rule3_html = rule4_html = ruleZ_html = skipped_html = ""

    if site_config and start and end and interval:
        # Normalize tokens: uppercase, strip underscores/dots/spaces
        tokens_raw = [t.strip() for t in site_config.replace(
            ",", " ").split() if t.strip()]
        tokens_norm = [_norm(t) for t in tokens_raw]

        # --- Case: UTDCO → all triplets from df_regions (supports "UT_DCO", "UTDCO", etc.) ---
        if len(tokens_norm) == 1 and tokens_norm[0] == "UTDCO":
            selected_triplets = df_regions["stationTriplet"].tolist()

        # --- Case: explicit triplets → accept directly (no CSV filter needed) ---
        elif tokens_raw and all(":" in t for t in tokens_raw):
            selected_triplets = tokens_raw  # flexible; runs even if not listed in CSV

        # --- Case: region names (normalized) ---
        elif tokens_norm and all(t in set(df_regions_norm["editingRegionNorm"].unique()) for t in tokens_norm):
            selected_triplets = df_regions_norm.loc[
                df_regions_norm["editingRegionNorm"].isin(
                    tokens_norm), "stationTriplet"
            ].tolist()

        else:
            selected_triplets = []

        # Update banner info
        selection_info = {"count": len(
            selected_triplets), "sample": selected_triplets[:5]}

        # --- Fetch data for each triplet ---
        all_station_results = []
        for site_triplet in selected_triplets:
            site_triplet_encoded = site_triplet.replace(":", "%3A")
            url = (
                "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?"
                f"stationTriplets={site_triplet_encoded}&elements=WTEQ,PREC,SNWD,SNDN&duration={interval}"
                f"&beginDate={start}&endDate={end}&periodRef=END"
                f"&centralTendencyType=NONE&returnFlags=false&returnOriginalValues=true&returnSuspectData=true"
            )
            api = requests.get(url)
            if api.status_code == 200:
                data = api.json()
                if data:
                    all_station_results.append(
                        {"stationTriplet": site_triplet, "data": data})
            else:
                print(f"Error {api.status_code} for {site_triplet}")

        # --- Run QC if we have results ---
        if all_station_results:
            results_all = check_qc_rules_all(all_station_results, df_regions)
            results = results_all

            # Pre-render consistent HTML for each table (minimal change)
            rule1_html = df_to_html(results["rule1"])
            rule3_html = df_to_html(results["rule3"])
            rule4_html = df_to_html(results["rule4"])
            ruleZ_html = df_to_html(results["ruleZ"])
            skipped_html = df_to_html(results["skipped"])

    # --- Render template ---
    return render_template_string(
        TEMPLATE,
        site_config=site_config,
        start=start,
        end=end,
        interval=interval,
      results=results,
      view=view,
        selection_info=selection_info,
        streamlit_url=STREAMLIT_URL,
        rule1_html=rule1_html,
        rule3_html=rule3_html,
        rule4_html=rule4_html,
        ruleZ_html=ruleZ_html,
        skipped_html=skipped_html,
    )

# ************ Run the app **********
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
