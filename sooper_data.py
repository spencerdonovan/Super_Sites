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
start_date = '2025-12-01'
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

    return df_dict

# %% Determine if Temperature bead is underneath snow or not

# for key, df in df_dict.items():

    # %%
# ---------------------------------------------
# Interactive Plot: PTEMP vs SNWD using Plotly
# ---------------------------------------------
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import plotly.io as pio


def ensure_local_plotly_js(js_filename='plotly.min.js'):
    if not os.path.exists(js_filename):
        tmp_html = '__plotly_tmp__.html'
        try:
            pio.write_html(go.Figure(), tmp_html, include_plotlyjs='directory', full_html=True, auto_open=False)
        finally:
            if os.path.exists(tmp_html):
                os.remove(tmp_html)


def create_interactive_plot(df_dict, title=None):
    # Prepare data: convert date to datetime and value to numeric
    proc = {}
    for k, df in df_dict.items():
        d = df.copy()
        if 'date' in d.columns:
            d['date'] = pd.to_datetime(d['date'])
        else:
            continue
        d['value'] = pd.to_numeric(d['value'], errors='coerce')
        d = d.set_index('date').sort_index()
        proc[k] = d['value']

    # Merge all series into one DataFrame
    if not proc:
        raise ValueError('No time series found in df_dict')

    merged = pd.concat(proc, axis=1)
    # Standard column names: SNWD and PTEMP_<height>
    if 'SNWD' not in merged.columns:
        print('Warning: SNWD column not found.')

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Plot SNWD hourly values as a black line on the secondary axis
    if 'SNWD' in merged.columns:
        fig.add_trace(
            go.Scatter(
                x=merged.index,
                y=merged['SNWD'],
                name='SNWD',
                line=dict(color='black', width=2),
                mode='lines',
                hovertemplate='%{x|%Y-%m-%d %H:%M}: SNWD=%{y:.2f}<extra></extra>'
            ),
            secondary_y=True
        )

    # Color palette for PTEMP: use evenly spaced hues for better separation between nearby depths
    ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]
    colors = [f'hsl({int(i * 137.508) % 360}, 70%, 45%)' for i in range(len(ptemp_cols))]

    # Get all midnight (00:00) timestamps to define comparison windows
    if 'SNWD' in merged.columns:
        midnight_idx = merged[merged.index.hour == 0].index.tolist()
        max_midnight_snwd = merged.loc[midnight_idx, 'SNWD'].max()
    else:
        midnight_idx = []
        max_midnight_snwd = None

    # Determine the group of PTEMP depths that could be buried at any point during this range
    buried_thresh = None
    buried_cols = []
    if max_midnight_snwd is not None:
        ptemp_heights = []
        for col in ptemp_cols:
            try:
                ptemp_heights.append(int(col.split('_', 1)[1]))
            except Exception:
                ptemp_heights.append(None)

        valid_heights = [h for h in ptemp_heights if h is not None]
        deeper_heights = [h for h in valid_heights if h > max_midnight_snwd]
        if deeper_heights:
            buried_thresh = min(deeper_heights)
            buried_cols = [col for col, h in zip(ptemp_cols, ptemp_heights) if h is not None and h < buried_thresh]
        else:
            buried_thresh = max(valid_heights) + 1 if valid_heights else None
            buried_cols = [col for col, h in zip(ptemp_cols, ptemp_heights) if h is not None]

        if buried_thresh is not None and buried_cols:
            thresh_label = f'PTEMP_{buried_thresh}'
            fig.add_annotation(
                x=0,
                y=1.08,
                xref='paper',
                yref='paper',
                text=f'Potentially buried PTEMP depths: < {thresh_label} ({len(buried_cols)} sensors)',
                showarrow=False,
                align='left',
                font=dict(size=12)
            )

    for i, col in enumerate(ptemp_cols):
        series = merged[col]
        color = colors[i % len(colors)]

        # Parse sensor height from PTEMP column name
        try:
            height = int(col.split('_', 1)[1])
        except Exception:
            height = None

        # Plot the full PTEMP line in light grey (no legend entry)
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series.values,
                name=col,
                line=dict(color='lightgrey', width=1),
                mode='lines',
                connectgaps=False,
                hoverinfo='skip',
                showlegend=False,
                legendgroup=col
            ),
            secondary_y=False
        )

        # Determine buried points using midnight SNWD and PTEMP height
        colored_mask = pd.Series(False, index=series.index, dtype=bool)
        for midnite in midnight_idx:
            snwd_val = merged.loc[midnite, 'SNWD']
            if pd.isna(snwd_val) or height is None:
                continue
            next_midnight = midnite + pd.Timedelta(hours=24)
            window = (series.index >= midnite) & (series.index < next_midnight)
            if snwd_val >= height:
                colored_mask.loc[window] = True

        colored_points = series.where(colored_mask)
        fig.add_trace(
            go.Scatter(
                x=colored_points.index,
                y=colored_points.values,
                name=col,
                mode='lines',
                line=dict(color=color, width=2),
                hovertemplate='%{x|%Y-%m-%d %H:%M}: %{y:.2f}<extra></extra>',
                legendgroup=col
            ),
            secondary_y=False
        )

    fig.update_layout(
        title=title or f"PTEMP heights vs SNWD for {site_triplet}",
        xaxis=dict(title='Date'),
        yaxis=dict(title='PTEMP (°C)'),
        yaxis2=dict(title='SNWD (cm)', overlaying='y', side='right'),
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0)
    )

    # Force x-axis to full data range (prevents auto-zoom to a smaller window)
    try:
        xmin = merged.index.min()
        xmax = merged.index.max()
        fig.update_xaxes(range=[xmin.strftime('%Y-%m-%d %H:%M:%S'), xmax.strftime('%Y-%m-%d %H:%M:%S')])
    except Exception:
        pass

    # Save interactive HTML for inspection and open
    try:
        out_html = 'ptemp_snwd_plot.html'
        fig.write_html(out_html, include_plotlyjs='cdn')
        print(f'Wrote interactive plot to {out_html}')
    except Exception as e:
        print('Could not write HTML:', e)

    fig.show()


def create_layered_html_plot(df_dict, title=None):
    ensure_local_plotly_js()

    # Use the same data processing as the regular interactive plot
    proc = {}
    for k, df in df_dict.items():
        d = df.copy()
        if 'date' in d.columns:
            d['date'] = pd.to_datetime(d['date'])
        else:
            continue
        d['value'] = pd.to_numeric(d['value'], errors='coerce')
        d = d.set_index('date').sort_index()
        proc[k] = d['value']

    if not proc:
        raise ValueError('No time series found in df_dict')

    merged = pd.concat(proc, axis=1)
    ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]
    colors = [f'hsl({int(i * 137.508) % 360}, 70%, 45%)' for i in range(len(ptemp_cols))]

    data = []
    trace_map = {}
    trace_index = 0

    if 'SNWD' in merged.columns:
        data.append({
            'x': merged.index.astype(str).tolist(),
            'y': merged['SNWD'].tolist(),
            'name': 'SNWD',
            'mode': 'lines',
            'line': {'color': 'black', 'width': 2},
            'yaxis': 'y2',
            'visible': True
        })
        trace_map['SNWD'] = [trace_index]
        trace_index += 1

    for i, col in enumerate(ptemp_cols):
        series = merged[col]
        color = colors[i % len(colors)]
        height = None
        try:
            height = int(col.split('_', 1)[1])
        except Exception:
            pass

        data.append({
            'x': series.index.astype(str).tolist(),
            'y': series.values.tolist(),
            'name': f'{col} baseline',
            'mode': 'lines',
            'line': {'color': 'lightgrey', 'width': 1},
            'visible': True,
            'showlegend': False
        })
        baseline_index = trace_index
        trace_index += 1

        colored_mask = pd.Series(False, index=series.index, dtype=bool)
        if 'SNWD' in merged.columns and height is not None:
            midnight_idx = merged[merged.index.hour == 0].index.tolist()
            for midnite in midnight_idx:
                snwd_val = merged.loc[midnite, 'SNWD']
                if pd.isna(snwd_val):
                    continue
                next_midnight = midnite + pd.Timedelta(hours=24)
                window = (series.index >= midnite) & (series.index < next_midnight)
                if snwd_val >= height:
                    colored_mask.loc[window] = True

        colored_points = series.where(colored_mask)
        data.append({
            'x': colored_points.index.astype(str).tolist(),
            'y': colored_points.values.tolist(),
            'name': col,
            'mode': 'lines',
            'line': {'color': color, 'width': 2},
            'visible': True
        })
        trace_map[col] = [baseline_index, trace_index]
        trace_index += 1

    layout = {
        'title': title or f'PTEMP heights vs SNWD for {site_triplet}',
        'xaxis': {'title': 'Date'},
        'yaxis': {'title': 'PTEMP (°C)'},
        'yaxis2': {'title': 'SNWD (cm)', 'overlaying': 'y', 'side': 'right'},
        'hovermode': 'x unified',
        'legend': {'orientation': 'h', 'yanchor': 'bottom', 'y': 1.02, 'xanchor': 'left', 'x': 0}
    }

    controls = []
    controls.append("<label><input type='checkbox' checked data-traces='[0]' value='SNWD'/> SNWD</label><br/>")
    for col in ptemp_cols:
        controls.append(f"<label><input type='checkbox' checked data-traces='{json.dumps(trace_map[col])}' value='{col}'/> {col}</label><br/>")

    html = f"""
<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>{title or 'PTEMP Layered Plot'}</title>
  <link rel='icon' href='data:;,='>
  <script src='plotly.min.js'></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; }}
    #container {{ display: flex; height: 100vh; }}
    #controls {{ width: 240px; padding: 12px; background: #f7f7f7; border-right: 1px solid #ddd; overflow-y: auto; }}
    #plot {{ flex: 1; }}
    .control-label {{ display: block; margin-bottom: 6px; font-size: 14px; }}
    h2 {{ margin-top: 0; font-size: 16px; }}
  </style>
</head>
<body>
  <div id='container'>
    <div id='controls'>
      <h2>Layers</h2>
      {''.join(controls)}
    </div>
    <div id='plot'></div>
  </div>
  <script>
    var fig = {json.dumps({'data': data, 'layout': layout}, default=str)};
    Plotly.newPlot('plot', fig.data, fig.layout, {{"responsive": true}});

    document.querySelectorAll('#controls input[type=checkbox]').forEach(function(input) {{
      input.addEventListener('change', function() {{
        var traces = JSON.parse(this.getAttribute('data-traces'));
        var visible = this.checked ? true : 'legendonly';
        Plotly.restyle('plot', {{visible: visible}}, traces);
      }});
    }});
  </script>
</body>
</html>
"""

    out_html = 'ptemp_leaflet_plot.html'
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Wrote layered HTML plot to {out_html}')


if __name__ == '__main__':
    df_dict = build_df_dict()
    try:
        create_layered_html_plot(df_dict)
    except Exception as e:
        print('Error creating layered HTML plot:', e)

