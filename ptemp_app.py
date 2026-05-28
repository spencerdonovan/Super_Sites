"""Flask app version of the PTEMP / SNWD dashboard.

This app reuses the same USDA AWDB data fetching and Plotly figure-building
logic as streamlit_app.py, but renders everything through Flask and HTML.
"""

import datetime
import functools
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import time
from flask import Flask, request, render_template_string

app = Flask(__name__)

SITE_OPTIONS = {
    'Powder Mountain': '1300:UT:SNTL',
    'Midway Valley': '626:UT:SNTL',
    'Trial Lake': '828:UT:SNTL'
}

ELEMENTS = 'PTEMP:*, SNWD::1'


@functools.lru_cache(maxsize=128)
def fetch_json(url, timeout=30, retries=3, backoff=1.5):
    """Fetch JSON from the AWDB API with retries."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json(), None
            error_message = f'HTTP {r.status_code} from API call.'
        except requests.exceptions.ReadTimeout as e:
            error_message = f'Read timeout (attempt {attempt}/{retries}): {e}'
        except Exception as e:
            error_message = f'Request failed (attempt {attempt}/{retries}): {e}'

        if attempt < retries:
            time_sleep = backoff ** attempt
            time.sleep(time_sleep)

    return None, error_message


@functools.lru_cache(maxsize=128)
def build_df_dict(site_triplet, start_date, end_date, interval, elements=ELEMENTS):
    """Build dataframes from AWDB response payload."""
    url = (
        'https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?'
        f'stationTriplets={site_triplet}&elements={elements}&duration={interval}'
        f'&beginDate={start_date}&endDate={end_date}&periodRef=END'
        '&centralTendencyType=NONE&returnFlags=true'
        '&returnOriginalValues=true&returnSuspectData=true'
    )

    json_data, error = fetch_json(url)
    if json_data is None:
        return {}, error

    data = json_data[0].get('data', [])
    df_dict = {}
    for item in data:
        elem = item['stationElement']['elementCode']
        if elem == 'PTEMP':
            hd = item['stationElement']['heightDepth']
            dict_key = f'{elem}_{hd}'
        elif elem == 'SNWD':
            dict_key = elem
        else:
            continue

        values = item.get('values', [])
        if not values:
            continue

        df = pd.DataFrame({
            'date': [v.get('date') for v in values],
            'value': [v.get('value') for v in values],
            'origValue': [v.get('origValue') for v in values],
            'qaFlag': [v.get('qaFlag') for v in values],
            'qcFlag': [v.get('qcFlag') for v in values]
        })
        df_dict[dict_key] = df

    return df_dict, None


def merge_time_series(df_dict):
    """Merge each series into a single DataFrame indexed by datetime."""
    proc = {}
    for key, df in df_dict.items():
        d = df.copy()
        if 'date' not in d.columns:
            continue
        d['date'] = pd.to_datetime(d['date'])
        d['value'] = pd.to_numeric(d['value'], errors='coerce')
        d = d.set_index('date').sort_index()
        proc[key] = d['value']

    if not proc:
        return pd.DataFrame()

    return pd.concat(proc, axis=1)


def build_plotly_figure(merged, selected_layers, show_snwd, title):
    """Build the PTEMP+SNWD line chart figure."""
    ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]
    colors = [f'hsl({int(i * 137.508) % 360}, 70%, 45%)' for i in range(len(ptemp_cols))]

    merged = merged.copy()
    if ptemp_cols:
        merged[ptemp_cols] = (merged[ptemp_cols] - 32.0) * 5.0 / 9.0

    fig = go.Figure()
    if show_snwd and 'SNWD' in merged.columns:
        fig.add_trace(
            go.Scatter(
                x=merged.index,
                y=merged['SNWD'],
                name='SNWD',
                line=dict(color='black', width=2),
                mode='lines',
                hovertemplate='%{x|%Y-%m-%d %H:%M}: SNWD=%{y:.2f}<extra></extra>',
                yaxis='y2'
            )
        )

    if 'SNWD' in merged.columns:
        midnight_idx = merged[merged.index.hour == 0].index.tolist()
    else:
        midnight_idx = []

    for i, col in enumerate(ptemp_cols):
        if col not in selected_layers:
            continue

        series = merged[col]
        color = colors[i % len(colors)]
        try:
            height = int(col.split('_', 1)[1])
        except Exception:
            height = None

        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series.values,
                name=f'{col} baseline',
                line=dict(color='lightgrey', width=1),
                mode='lines',
                hoverinfo='skip',
                showlegend=False
            )
        )

        colored_mask = pd.Series(False, index=series.index, dtype=bool)
        if height is not None and midnight_idx:
            for midnite in midnight_idx:
                snwd_val = merged.loc[midnite, 'SNWD']
                if pd.isna(snwd_val):
                    continue
                next_midnight = midnite + pd.Timedelta(hours=24)
                window = (series.index >= midnite) & (series.index < next_midnight)
                if snwd_val >= height:
                    colored_mask.loc[window] = True

        colored_points = series.where(colored_mask)
        if colored_mask.any():
            fig.add_trace(
                go.Scatter(
                    x=colored_points.index,
                    y=colored_points.values,
                    name=col,
                    legendgroup=col,
                    line=dict(color=color, width=2),
                    mode='lines',
                    hovertemplate=f'{col}: %{{y:.2f}} °C<br>%{{x|%Y-%m-%d %H:%M}}<extra></extra>'
                )
            )
        else:
            fig.add_trace(
                go.Scatter(
                    x=series.index,
                    y=series.values,
                    name=col,
                    legendgroup=col,
                    showlegend=True,
                    visible='legendonly',
                    line=dict(color=color, width=2),
                    mode='lines',
                    hovertemplate=f'{col}: %{{y:.2f}} °C<br>%{{x|%Y-%m-%d %H:%M}}<extra></extra>'
                )
            )

    fig.update_layout(
        title={'text': title, 'y': 0.99, 'x': 0.01, 'xanchor': 'left', 'yanchor': 'top'},
        xaxis=dict(title='Date', uirevision='static'),
        yaxis=dict(title='PTEMP (°C)', uirevision='static'),
        yaxis2=dict(title='SNWD (in)', overlaying='y', side='right', uirevision='static'),
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='top', y=-0.20, xanchor='center', x=0.5, groupclick='togglegroup'),
        margin=dict(l=40, r=40, t=100, b=120),
        height=700,
        dragmode='zoom',
        uirevision='static'
    )

    return fig


def build_heatmap_figure(merged, selected_layers, show_snwd, title):
    """Build the PTEMP heatmap figure."""
    ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]
    if not ptemp_cols:
        return go.Figure()

    merged = merged.copy()
    merged[ptemp_cols] = (merged[ptemp_cols] - 32.0) * 5.0 / 9.0

    depth_pairs = []
    for c in ptemp_cols:
        try:
            depth = int(c.split('_', 1)[1])
        except Exception:
            depth = None
        if depth is not None and depth >= 0:
            depth_pairs.append((c, depth))

    if not depth_pairs:
        return go.Figure()

    depth_pairs.sort(key=lambda x: x[1])
    col_order = [p[0] for p in depth_pairs]
    depths = np.array([p[1] for p in depth_pairs], dtype=float)

    if len(depths) > 1:
        min_gap = np.min(np.diff(np.unique(depths)))
        resolution = min(1.0, float(min_gap) / 4.0)
    else:
        resolution = 1.0

    interp_heights = np.arange(depths.min(), depths.max() + resolution, resolution)
    interp_heights = np.round(interp_heights, 3)

    z = np.full((len(interp_heights), len(merged.index)), np.nan)
    source_values = None
    for col_idx, col in enumerate(col_order):
        z_src = merged[col].to_numpy(dtype=float)
        if col_idx == 0:
            source_values = np.vstack([z_src])
        else:
            source_values = np.vstack([source_values, z_src])

    for time_index in range(z.shape[1]):
        valid = ~np.isnan(source_values[:, time_index])
        if np.count_nonzero(valid) >= 2:
            z[:, time_index] = np.interp(
                interp_heights,
                depths[valid],
                source_values[valid, time_index],
                left=source_values[valid, time_index][0],
                right=source_values[valid, time_index][-1]
            )
        elif np.count_nonzero(valid) == 1:
            z[:, time_index] = source_values[valid, time_index][0]

    if show_snwd and 'SNWD' in merged.columns:
        max_snwd = merged['SNWD'].max()
        if pd.isna(max_snwd):
            max_snwd = 126
    else:
        max_snwd = 126

    interp_heights = interp_heights[interp_heights <= max_snwd]
    z = z[: len(interp_heights), :]

    z_min = np.nanmin(z)
    z_max = np.nanmax(z)

    fig = go.Figure()
    fig.add_trace(
        go.Heatmap(
            x=merged.index,
            y=interp_heights,
            z=z,
            colorscale='RdBu_r',
            zmid=0,
            zmin=z_min,
            zmax=z_max,
            colorbar=dict(title='PTEMP (°C)'),
            xgap=0,
            ygap=0,
            zsmooth='best',
            hoverongaps=False,
            hovertemplate='Height: %{y} in<br>%{x|%Y-%m-%d %H:%M}<br>PTEMP: %{z:.2f} °C<extra></extra>'
        )
    )

    if show_snwd and 'SNWD' in merged.columns:
        fig.add_trace(
            go.Scatter(
                x=merged.index,
                y=merged['SNWD'],
                name='SNWD',
                line=dict(color='black', width=2),
                mode='lines',
                hovertemplate='%{x|%Y-%m-%d %H:%M}: SNWD=%{y:.2f} in<extra></extra>',
                yaxis='y2'
            )
        )

    layout = dict(
        title={'text': f'{title} — PTEMP heatmap', 'y': 0.99, 'x': 0.01, 'xanchor': 'left', 'yanchor': 'top'},
        xaxis=dict(title='Date', type='date', uirevision='static'),
        yaxis=dict(
            title='Height (in)',
            autorange=False,
            range=[0, max_snwd],
            tickmode='array',
            tickvals=[d for d in depths if d <= max_snwd],
            ticktext=[str(int(v)) if float(v).is_integer() else str(v) for v in depths if v <= max_snwd],
            uirevision='static'
        ),
        margin=dict(l=60, r=60, t=100, b=120),
        height=520,
        hovermode='x unified'
    )

    if show_snwd and 'SNWD' in merged.columns:
        layout['yaxis2'] = dict(
            title='SNWD (in)', overlaying='y', side='right', showgrid=False, uirevision='static'
        )

    fig.update_layout(**layout)
    return fig


def _normalize_selected_layers(args, ptemp_cols):
    selected = args.getlist('selected_layers')
    if selected:
        return [c for c in selected if c in ptemp_cols]
    return ptemp_cols


@app.route('/', methods=['GET'])
def index():
    station_name = request.args.get('station', list(SITE_OPTIONS.keys())[0])
    interval = request.args.get('interval', 'HOURLY')
    start_date = request.args.get('start', datetime.date(2025, 12, 1).isoformat())
    end_date = request.args.get('end', datetime.date(2026, 5, 8).isoformat())
    hide_never_buried = request.args.get('hide_never_buried') == 'on'
    show_snwd = request.args.get('show_snwd') != 'off'
    show_data_table = request.args.get('show_data_table') == 'on'

    errors = []
    fig_html = None
    heatmap_html = None
    data_table_html = ''
    selected_layers = []
    available_layers = []

    if station_name not in SITE_OPTIONS:
        station_name = list(SITE_OPTIONS.keys())[0]

    if interval not in ['HOURLY', 'DAILY']:
        interval = 'HOURLY'

    if start_date > end_date:
        errors.append('Start date must be on or before end date.')
    else:
        site_triplet = SITE_OPTIONS[station_name]
        df_dict, fetch_error = build_df_dict(site_triplet, start_date, end_date, interval)
        if fetch_error:
            errors.append(fetch_error)
        elif not df_dict:
            errors.append('No data available for the selected station/date range.')
        else:
            merged = merge_time_series(df_dict)
            if merged.empty:
                errors.append('No valid time series could be created from the API results.')
            else:
                ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]
                available_layers = []
                for c in ptemp_cols:
                    try:
                        if int(c.split('_', 1)[1]) >= 0:
                            available_layers.append(c)
                    except Exception:
                        available_layers.append(c)

                never_buried = []
                if 'SNWD' in merged.columns:
                    midnight_idx = merged[merged.index.hour == 0].index.tolist()
                    for col in ptemp_cols:
                        try:
                            h = int(col.split('_', 1)[1])
                        except Exception:
                            h = None
                        if h is None or not midnight_idx:
                            continue
                        snw_at_midnights = merged.loc[midnight_idx, 'SNWD']
                        if not (snw_at_midnights >= h).any():
                            never_buried.append(col)

                if hide_never_buried and never_buried:
                    available_layers = [c for c in available_layers if c not in never_buried]

                selected_layers = _normalize_selected_layers(request.args, available_layers)
                if not selected_layers:
                    selected_layers = available_layers.copy()

                title = f'PTEMP heights vs SNWD for {station_name} ({interval})'
                fig = build_plotly_figure(merged, selected_layers, show_snwd, title)
                fig_html = pio.to_html(fig, full_html=False, include_plotlyjs=True)

                heatmap_fig = build_heatmap_figure(merged, selected_layers, show_snwd, title)
                if heatmap_fig.data:
                    heatmap_html = pio.to_html(heatmap_fig, full_html=False, include_plotlyjs=False)

                if show_data_table:
                    data_table_html = merged.to_html(classes='data-table', border=0, na_rep='', justify='left')

    return render_template_string(
        HTML_TEMPLATE,
        SITE_OPTIONS=SITE_OPTIONS,
        station_name=station_name,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        hide_never_buried=hide_never_buried,
        show_snwd=show_snwd,
        show_data_table=show_data_table,
        errors=errors,
        fig_html=fig_html,
        heatmap_html=heatmap_html,
        data_table_html=data_table_html,
        available_layers=available_layers,
        selected_layers=selected_layers,
        never_buried=never_buried,
    )


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>PTEMP / SNWD Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; background: #f8fbff; }
    .container { max-width: 1280px; margin: 0 auto; }
    h1 { color: #1f3c88; margin-bottom: 0.25em; }
    .top-note { color: #444; margin-bottom: 1.2em; }
    .form-grid { display: grid; grid-template-columns: minmax(220px, 260px) 1fr; gap: 18px; align-items: start; }
    fieldset { background: white; border: 1px solid #d9e2ef; border-radius: 8px; padding: 18px; }
    legend { font-weight: 700; }
    label { display: block; margin-bottom: 8px; font-size: 14px; color: #1f2a44; }
    select, input[type=date], input[type=text], .multi-select { width: 100%; padding: 8px 10px; border: 1px solid #c5d1e5; border-radius: 6px; }
    .checkboxes { display: grid; gap: 10px; }
    .button-row { margin-top: 14px; }
    button { background: #2c7be5; color: white; border: none; border-radius: 6px; padding: 10px 18px; cursor: pointer; font-size: 15px; }
    button:hover { background: #2559a6; }
    .error { color: #c53030; margin-bottom: 14px; }
    .chart-wrapper { margin-top: 24px; padding: 18px; background: white; border-radius: 10px; border: 1px solid #d9e2ef; }
    .chart-wrapper h2 { margin-top: 0; }
    .notice { margin-top: 14px; padding: 12px 14px; border-radius: 8px; background: #eff4ff; color: #1f3c88; border: 1px solid #c5d1e5; }
    .data-table { border-collapse: collapse; width: 100%; margin-top: 18px; }
    .data-table th, .data-table td { border: 1px solid #d9e2ef; padding: 8px 10px; text-align: left; }
    .data-table th { background: #f0f4ff; }
    .form-actions { margin-top: 16px; }
    .layer-select { min-height: 180px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>PTEMP + SNWD Dashboard</h1>
    <p class="top-note">Browse station PTEMP heights, compare SNWD, and inspect buried temperature layers using USDA AWDB data.</p>

    {% if errors %}
      <div class="error"><strong>Issues:</strong><br>{{ errors | join('<br>') | safe }}</div>
    {% endif %}

    <form method="get">
      <fieldset>
        <legend>Data selection</legend>
        <div class="form-grid">
          <div>
            <label for="station">Station</label>
            <select id="station" name="station">
              {% for name in SITE_OPTIONS.keys() %}
                <option value="{{ name }}" {% if name == station_name %}selected{% endif %}>{{ name }}</option>
              {% endfor %}
            </select>

            <label for="interval">Interval</label>
            <select id="interval" name="interval">
              <option value="HOURLY" {% if interval == 'HOURLY' %}selected{% endif %}>HOURLY</option>
              <option value="DAILY" {% if interval == 'DAILY' %}selected{% endif %}>DAILY</option>
            </select>

            <label for="start">Start date</label>
            <input type="date" id="start" name="start" value="{{ start_date }}">

            <label for="end">End date</label>
            <input type="date" id="end" name="end" value="{{ end_date }}">
          </div>

          <div>
            <label for="selected_layers">PTEMP layers to show</label>
            <select id="selected_layers" name="selected_layers" multiple class="layer-select">
              {% for layer in available_layers %}
                <option value="{{ layer }}" {% if layer in selected_layers %}selected{% endif %}>{{ layer }}</option>
              {% endfor %}
            </select>

            <div class="checkboxes">
              <label><input type="checkbox" name="hide_never_buried" {% if hide_never_buried %}checked{% endif %}> Hide never-buried PTEMP layers</label>
              <label><input type="checkbox" name="show_snwd" {% if show_snwd %}checked{% endif %}> Show SNWD</label>
              <label><input type="checkbox" name="show_data_table" {% if show_data_table %}checked{% endif %}> Show raw data table</label>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <button type="submit">Update dashboard</button>
        </div>
      </fieldset>
    </form>

    {% if never_buried and hide_never_buried %}
      <div class="notice">Hiding {{ never_buried|length }} never-buried PTEMP layer(s).</div>
    {% endif %}

    {% if not available_layers %}
      <div class="notice">No PTEMP layers were available for that station/date range. The chart below may show only SNWD.</div>
    {% endif %}

    {% if fig_html %}
      <div class="chart-wrapper">
        <h2>PTEMP / SNWD profile</h2>
        {{ fig_html | safe }}
      </div>
    {% endif %}

    {% if heatmap_html %}
      <div class="chart-wrapper">
        <h2>PTEMP vertical profile heatmap</h2>
        {{ heatmap_html | safe }}
      </div>
    {% endif %}

    {% if data_table_html %}
      <div class="chart-wrapper">
        <h2>Raw merged time series</h2>
        {{ data_table_html | safe }}
      </div>
    {% endif %}

    <div class="notice">
      <p>Notes:</p>
      <ul>
        <li>PTEMP sensor heights are shown as colored segments when snow depth at midnight was equal to or deeper than the sensor depth.</li>
        <li>Use the layer selector to hide or show individual PTEMP traces.</li>
        <li>The dashboard uses USDA AWDB REST API data for the selected station and date range.</li>
      </ul>
    </div>
  </div>
</body>
</html>
"""


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
