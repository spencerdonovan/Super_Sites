"""Streamlit dashboard for USDA AWDB PTEMP and SNWD data.

This app fetches temperature and snow depth data from the USDA AWDB REST API,
remaps PTEMP from Fahrenheit to Celsius, and renders an interactive Plotly chart.
The chart supports zooming and lets the user toggle PTEMP depth layers and SNWD.
"""

import requests
import pandas as pd
import datetime
import time
import streamlit as st

# Map station names to AWDB station triplets.
SITE_OPTIONS = {
    'Powder Mountain': '1300:UT:SNTL',
    'Midway Valley': '626:UT:SNTL',
    'Trial Lake': '828:UT:SNTL'
}

# The API query requests all PTEMP depths plus SNWD for the selected station.
ELEMENTS = 'PTEMP:*, SNWD::1'


@st.cache_data(show_spinner=False)
def fetch_json(url, timeout=15, retries=3, backoff=1.5):
    """Fetch JSON from the AWDB API with simple retry/backoff behavior."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            st.warning(f'HTTP {r.status_code} from API call')
        except Exception as e:
            st.warning(f'Request failed (attempt {attempt}/{retries}): {e}')

        # Exponential backoff between retries.
        if attempt < retries:
            sleep_time = backoff ** attempt
            time.sleep(sleep_time)

    st.error('Failed to fetch data after retries.')
    return None


@st.cache_data(show_spinner=False)
def build_df_dict(site_triplet, start_date, end_date, interval, elements=ELEMENTS):
    """Build a dictionary of pandas DataFrames from API response data."""
    url = (
        'https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data?'
        f'stationTriplets={site_triplet}&elements={elements}&duration={interval}'
        f'&beginDate={start_date}&endDate={end_date}&periodRef=END'
        '&centralTendencyType=NONE&returnFlags=true'
        '&returnOriginalValues=true&returnSuspectData=true'
    )

    json_data = fetch_json(url)
    if json_data is None:
        return {}

    data = json_data[0].get('data', [])
    df_dict = {}

    # Each item contains a station element and a time series of values.
    for item in data:
        elem = item['stationElement']['elementCode']

        # Build a unique key for each PTEMP sensor depth, but only one key for SNWD.
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

    return df_dict


def merge_time_series(df_dict):
    """Convert each series to a datetime index and merge into one DataFrame."""
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

    # Resulting DataFrame has a column for each sensor series.
    return pd.concat(proc, axis=1)


def build_plotly_figure(merged, selected_layers, show_snwd, title):
    """Build the Plotly figure with SNWD on a secondary y-axis and PTEMP depth lines."""
    import plotly.graph_objects as go

    # Use an HSL palette for PTEMP traces so each line is visually distinct.
    ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]
    colors = [f'hsl({int(i * 137.508) % 360}, 70%, 45%)' for i in range(len(ptemp_cols))]

    # Keep original data untouched; convert only for plotting.
    merged = merged.copy()
    if ptemp_cols:
        merged[ptemp_cols] = (merged[ptemp_cols] - 32.0) * 5.0 / 9.0

    fig = go.Figure()

    # Add SNWD to the secondary axis if requested.
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

    # Use midnight values to determine periods where snow depth covers each PTEMP height.
    if 'SNWD' in merged.columns:
        midnight_idx = merged[merged.index.hour == 0].index.tolist()
        max_midnight_snwd = merged.loc[midnight_idx, 'SNWD'].max() if midnight_idx else None
    else:
        midnight_idx = []
        max_midnight_snwd = None

    for i, col in enumerate(ptemp_cols):
        if col not in selected_layers:
            continue

        series = merged[col]
        color = colors[i % len(colors)]

        # Attempt to parse the sensor depth from the column name.
        try:
            height = int(col.split('_', 1)[1])
        except Exception:
            height = None

        # Plot the full PTEMP series in grey as a baseline line.
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series.values,
                name=f'{col} baseline',
                line=dict(color='grey', width=1),
                mode='lines',
                hoverinfo='skip',
                showlegend=False
            )
        )

        # Highlight periods where snow depth was greater than or equal to the sensor height.
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
        has_coverage = colored_mask.any()
        
        if has_coverage:
            # Buried layers: show colored trace by default
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
            # Non-buried layers: keep the plot grey by default, but use a hidden colored
            # trace for the legend so behavior matches buried PTEMP traces.
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
        legend=dict(orientation='h', yanchor='top', y=-0.18, xanchor='center', x=0.5, groupclick='togglegroup'),
        margin=dict(l=40, r=40, t=100, b=120),
        height=828,
        dragmode='zoom',
        uirevision='static'
    )

    return fig


def main():
    """Main Streamlit app layout and behavior."""
    st.set_page_config(page_title='PTEMP / SNWD Dashboard', layout='wide')
    st.title('PTEMP + SNWD Dashboard')
    st.markdown('Browse station PTEMP heights, compare SNWD, and inspect buried temperature layers.')

    with st.sidebar:
        st.header('Data selection')

        # User controls in the sidebar.
        station_name = st.selectbox('Station', list(SITE_OPTIONS.keys()), index=0)
        site_triplet = SITE_OPTIONS[station_name]
        interval = st.radio('Interval', ['HOURLY', 'DAILY'])

        default_start = datetime.date(2025, 12, 1)
        default_end = datetime.date(2026, 5, 8)
        start_date = st.date_input('Start date', default_start)
        end_date = st.date_input('End date', default_end)

        if start_date > end_date:
            st.error('Start date must be on or before end date.')
            return

        df_dict = build_df_dict(site_triplet, start_date.isoformat(), end_date.isoformat(), interval)
        if not df_dict:
            st.warning('No data available for the selected station/date range.')
            return

        merged = merge_time_series(df_dict)
        if merged.empty:
            st.warning('No valid time series could be created from the API results.')
            return

        # List available PTEMP depth traces and allow user selection.
        ptemp_cols = [c for c in merged.columns if c.startswith('PTEMP')]

        # Determine which PTEMP layers are ever buried (based on midnight SNWD)
        never_buried = []
        if 'SNWD' in merged.columns:
            try:
                midnight_idx = merged[merged.index.hour == 0].index.tolist()
            except Exception:
                midnight_idx = []

            for col in ptemp_cols:
                try:
                    h = int(col.split('_', 1)[1])
                except Exception:
                    h = None
                if h is None or not midnight_idx:
                    # treat as potentially buried unless we can prove otherwise
                    continue

                # Check if any midnight snow depth >= sensor height
                snw_at_midnights = merged.loc[midnight_idx, 'SNWD']
                if not (snw_at_midnights >= h).any():
                    never_buried.append(col)

        hide_never_buried = st.checkbox('Hide never-buried PTEMP layers', value=False)

        # Build the options presented in the multiselect according to the toggle
        available_cols = [c for c in ptemp_cols if not (hide_never_buried and c in never_buried)]
        default_selected = available_cols.copy()
        selected_layers = st.multiselect('PTEMP layers to show', available_cols, default=default_selected)

        if hide_never_buried and never_buried:
            st.caption(f'Hiding {len(never_buried)} never-buried layer(s)')

        show_snwd = st.checkbox('Show SNWD', value=True)
        show_data_table = st.checkbox('Show raw data', value=False)

    title = f'PTEMP heights vs SNWD for {station_name} ({interval})'
    fig = build_plotly_figure(merged, selected_layers, show_snwd, title)

    # Render the Plotly figure in the app with a static key to preserve zoom/pan state.
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True}, key='ptemp_snwd_chart')

    if show_data_table:
        st.subheader('Raw merged time series')
        st.dataframe(merged)

    st.markdown('---')
    st.markdown('### Notes')
    st.markdown(
        '- PTEMP sensor heights are shown as colored segments when the snow depth at the next midnight was equal to or deeper than the sensor depth.\n'
        '- Use the legend or the sidebar multiselect to hide/show individual PTEMP traces.\n'
        '- The dashboard uses USDA AWDB REST API data for the selected station and date range.'
    )


if __name__ == '__main__':
    main()
