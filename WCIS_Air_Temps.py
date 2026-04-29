#!/usr/bin/env python3
"""
WCIS SNOTEL multi-block text parser and comparison of TOBS.I-1 vs TOBS.I-98.

- Parses WCIS text report blocks (e.g., 714.1 / 714.3) with multi-row headers (and optional numeric index row).
- Composes compound column names (element + position), e.g., TOBS.I-1, TOBS.I-98.
- Cleans QA suffixes (VR, VP, NR, EP, SR) from numeric fields.
- Joins I-1 and I-98 TOBS on DATE+TIME and computes differences.
- Prints per-block debug headers so you can see exactly what was parsed.

Run in Spyder: simply press Run (no command-line args needed).
"""

import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import requests
import pandas as pd

# -----------------------------
# Configuration (edit as needed)
# -----------------------------
STATION_ID = 714
BEGIN_DT = datetime(2026, 4, 24, 0, 0)
END_DT = datetime(2026, 4, 27, 23, 59)
THRESHOLD = 0.5   # absolute difference threshold in degC
DATA_PER_DAY = "All"
DEBUG = True       # Set True to print discovered columns per block

# -----------------------------
# URL builder
# -----------------------------


def month_str(dt: datetime) -> str:
    """Return 3-letter month (WCIS expects e.g., Apr, May)."""
    return dt.strftime("%b")


def build_wcis_url() -> str:
    """
    Construct the WCIS SNOTEL report URL (format=text).
    NOTE: Use '&' between params (not HTML '&amp;').
    """
    base = "https://wcis.sc.egov.usda.gov/wcis/snotelReports/"
    params = (
        f"?station={STATION_ID}"
        f"&selectedBy=channel&group=&channel=&snotelDateRange="
        f"&beginMonth={month_str(BEGIN_DT)}&beginDay={BEGIN_DT.day}&beginYear={BEGIN_DT.year}"
        f"&beginHour={BEGIN_DT.hour}&beginMinute={BEGIN_DT.minute}"
        f"&endMonth={month_str(END_DT)}&endDay={END_DT.day}&endYear={END_DT.year}"
        f"&endHour={END_DT.hour}&endMinute={END_DT.minute}"
        f"&dataPerDay={DATA_PER_DAY}"
        f"&snowNonreportingDays=true&reportType=gtk&format=text&fileName="
        f"&showQaFlag=true&granularity=group&sortOrder=channel&submitButton=Submit"
    )
    return base + params


# -----------------------------
# Parsing helpers
# -----------------------------
SEP_RX = re.compile(r"\s{2,}")             # split on 2+ spaces
RE_HORIZONTAL = re.compile(r'^[\s\-\=\+]+$')
RE_NUM = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)')  # numeric prefix
POS_TOKEN_RX = re.compile(r'^[A-Z]-\d+$')         # I-1, D-98, etc.

# Hints to identify units lines
UNIT_TOKEN_HINT = {"degc", "deg c", "deg_c",
                   "in", "pct", "gram/l", "unitless", "volt"}

# Common SNOTEL element names to help classify element row
KNOWN_ELEMENTS = {
    "BATT", "WTEQ", "PREC", "TOBS", "TMAX", "TMIN", "TAVG", "SNWD",
    "SMS", "STO", "SAL", "RDC",
    # add more if needed: "WDIRV", "WSPDV", "LRADT", etc.
}


def strip_qa(val: str):
    """Extract numeric prefix from values like '1.7VP', '-1SR', '14.6VR'."""
    if val is None:
        return pd.NA
    s = str(val).strip()
    m = RE_NUM.match(s)
    return float(m.group(1)) if m else pd.NA


def is_date_header(line: str) -> bool:
    """Detect the 'DATE       TIME  #' header line."""
    s = line.strip()
    return s.startswith("DATE") and "TIME" in s and "#" in s


def looks_like_positions(tokens: List[str]) -> bool:
    # positions are uppercase letter + dash + digits
    return tokens and all(POS_TOKEN_RX.match(t) for t in tokens)


def looks_like_units(tokens: List[str]) -> bool:
    # units line typically contains any of the hints (case-insensitive)
    tl = [t.lower() for t in tokens]
    return any(
        (h in " ".join(tl)) or (h in tl)  # allow "degC" variants
        for h in UNIT_TOKEN_HINT
    )


def looks_like_elements(tokens: List[str]) -> bool:
    # elements are alphabetic names (TOBS, TMAX, SNWD, etc.)
    # Require tokens to be alpha and intersect with known elements
    alpha = [t for t in tokens if t.isalpha()]
    return bool(alpha) and any(t in KNOWN_ELEMENTS for t in alpha)


def find_header_triplet(lines: List[str], idx_date_hdr: int) -> Tuple[List[str], List[str], List[str]]:
    """
    Scan upward from idx_date_hdr to find the three header rows:
      elements, positions, units
    Skips an optional numeric '1 2 3 ...' line.
    Returns (elements, positions, units) as token lists.
    """
    # Look up to 15 lines above; some tables include extra banners
    search_range = range(idx_date_hdr - 15, idx_date_hdr)
    candidates = []
    for j in search_range:
        if j < 0:
            continue
        line = lines[j].strip()
        if not line or RE_HORIZONTAL.match(line):
            continue
        tokens = [t.strip() for t in SEP_RX.split(line) if t.strip()]
        # Skip numeric index lines (all tokens are digits)
        if tokens and all(t.isdigit() for t in tokens):
            continue
        candidates.append((j, tokens))

    elements_line = positions_line = units_line = None

    # First pass: strong classification
    for j, tokens in candidates:
        if looks_like_positions(tokens) and positions_line is None:
            positions_line = (j, tokens)
        elif looks_like_units(tokens) and units_line is None:
            units_line = (j, tokens)
        elif looks_like_elements(tokens) and elements_line is None:
            elements_line = (j, tokens)

    # If any piece is missing, try a second pass with relaxed rules
    if not (elements_line and positions_line and units_line):
        for j, tokens in candidates:
            # Relaxed elements: all alpha tokens of len>=2
            if elements_line is None and all(t.isalpha() and len(t) >= 2 for t in tokens):
                elements_line = (j, tokens)
            # Relaxed positions: majority look like A-#
            if positions_line is None:
                pos_like = sum(1 for t in tokens if POS_TOKEN_RX.match(t))
                if pos_like >= max(1, len(tokens) // 2):
                    positions_line = (j, tokens)
            # Relaxed units: any token containing digits+units marker (degC/in/etc.)
            if units_line is None:
                if any(any(h in t.lower() for h in UNIT_TOKEN_HINT) for t in tokens):
                    units_line = (j, tokens)

    if not (elements_line and positions_line and units_line):
        raise ValueError(
            "Could not identify elements/positions/units header rows above the data header.")

    elements = [t.strip() for t in elements_line[1]]
    positions = [t.strip() for t in positions_line[1]]
    units = [t.strip() for t in units_line[1]]

    # If lengths mismatch (rare), truncate to min length to stay aligned
    n = min(len(elements), len(positions))
    return elements[:n], positions[:n], units[:n]


def parse_block(lines: List[str], idx_date_hdr: int) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Parse a single block of data starting at the 'DATE TIME #' header index.
    """
    # Try to capture a block ID above the header, e.g., "... 714.3"
    block_id = None
    for back in range(4, 20):  # search a bit farther
        j = idx_date_hdr - back
        if j >= 0 and lines[j].strip():
            m = re.search(r'(\d{3,}\.\d+)$', lines[j].strip())
            if m:
                block_id = m.group(1)
                break

    # Dynamic header detection
    elements, positions, units = find_header_triplet(lines, idx_date_hdr)
    compound_cols = [f"{e}.{p}" for e, p in zip(elements, positions)]

    if DEBUG:
        print(f"[DEBUG] Block {block_id or '?'}")
        print(f"        Elements : {elements}")
        print(f"        Positions: {positions}")
        print(f"        Units    : {units}")
        print(f"        Columns  : {compound_cols}")

    # Build data rows until next block or END
    data_rows = []
    i = idx_date_hdr + 1
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if not line.strip():
            break
        if "********************" in line or is_date_header(line) or line.strip() == "END":
            break
        parts = [t for t in SEP_RX.split(line.strip()) if t != ""]
        if len(parts) < 3:
            i += 1
            continue
        date, time, seq = parts[:3]
        values = parts[3:]
        # pad/truncate to fit columns
        if len(values) < len(compound_cols):
            values = values + ([""] * (len(compound_cols) - len(values)))
        elif len(values) > len(compound_cols):
            values = values[:len(compound_cols)]
        row = {"DATE": date, "TIME": time, "#": seq}
        for name, val in zip(compound_cols, values):
            row[name] = val
        data_rows.append(row)
        i += 1

    df = pd.DataFrame(data_rows)
    if not df.empty:
        df["timestamp"] = df["DATE"].astype(str) + " " + df["TIME"].astype(str)
    meta = {"block_id": block_id} if block_id else {}
    return df, meta


def parse_all_blocks(text: str) -> List[pd.DataFrame]:
    """
    Parse every 'DATE TIME #' block in the WCIS text report.
    Returns a list of DataFrames with compound column names.
    """
    lines = [ln for ln in text.splitlines()]
    date_hdr_indices = [i for i, ln in enumerate(lines) if is_date_header(ln)]
    dfs = []
    for idx in date_hdr_indices:
        df, meta = parse_block(lines, idx)
        df.attrs.update(meta)
        dfs.append(df)
    return dfs

# -----------------------------
# Comparison workflow
# -----------------------------


def compare_tobs_i1_vs_i98(text: str, threshold: float = THRESHOLD) -> pd.DataFrame:
    """
    Parse the report text, extract TOBS.I-1 and TOBS.I-98 columns, merge by timestamp,
    clean QA suffixes, and compute differences.
    """
    dfs = parse_all_blocks(text)

    # Show block IDs and columns if debugging
    if DEBUG:
        for df in dfs:
            print(f"[DEBUG] Parsed block {df.attrs.get('block_id')} with {len(df)} rows and columns:\n"
                  f"        {list(df.columns)}")

    # Find blocks containing TOBS.I-1 and TOBS.I-98
    df_i1 = None
    df_i98 = None
    for df in dfs:
        cols = list(df.columns)
        has_i1 = any(c.startswith("TOBS.") and c.endswith("I-1") for c in cols)
        has_i98 = any(c.startswith("TOBS.") and c.endswith("I-98")
                      for c in cols)
        if has_i1:
            df_i1 = df
        if has_i98:
            df_i98 = df

    if df_i1 is None or df_i98 is None:
        raise ValueError(
            "Could not locate TOBS.I-1 and/or TOBS.I-98 in the parsed blocks. "
            "Check the date range or station configuration."
        )

    # The actual column names (in case of extra spaces) by searching prefix/suffix
    col_i1 = [c for c in df_i1.columns if c.startswith(
        "TOBS.") and c.endswith("I-1")][0]
    col_i98 = [c for c in df_i98.columns if c.startswith(
        "TOBS.") and c.endswith("I-98")][0]

    # Prepare minimal frames
    a = df_i1[["timestamp", col_i1]].copy()
    b = df_i98[["timestamp", col_i98]].copy()

    # Clean numeric values
    a["TOBS.I-1"] = a[col_i1]
    b["TOBS.I-98"] = b[col_i98]
    a["TOBS.I-1_num"] = a["TOBS.I-1"].apply(strip_qa)
    b["TOBS.I-98_num"] = b["TOBS.I-98"].apply(strip_qa)

    # Merge by timestamp
    comp = pd.merge(a[["timestamp", "TOBS.I-1", "TOBS.I-1_num"]],
                    b[["timestamp", "TOBS.I-98", "TOBS.I-98_num"]],
                    on="timestamp", how="inner")

    comp["diff"] = comp["TOBS.I-98_num"] - comp["TOBS.I-1_num"]
    comp["abs_diff"] = comp["diff"].abs()
    comp["exceeds_threshold"] = comp["abs_diff"] > threshold

    return comp


def print_summary(comp_df: pd.DataFrame, threshold: float = THRESHOLD):
    """Print concise stats and sample mismatches."""
    if comp_df.empty:
        print("No overlapping timestamps between I-1 and I-98 TOBS blocks.")
        return

    total = len(comp_df)
    valid = comp_df[["TOBS.I-1_num", "TOBS.I-98_num"]].dropna().shape[0]
    exceeded = int(comp_df["exceeds_threshold"].sum())
    mean_diff = comp_df["diff"].mean(skipna=True)
    max_abs = comp_df["abs_diff"].max(skipna=True)
    corr = comp_df[["TOBS.I-1_num", "TOBS.I-98_num"]].corr().iloc[0, 1]

    print("\n=== TOBS I-1 vs I-98 Comparison ===")
    print(f"Rows merged on timestamp:     {total}")
    print(f"Rows with numeric values:     {valid}")
    print(f"Threshold (absolute):         {threshold}")
    print(f"Rows exceeding threshold:     {exceeded}")
    print(f"Mean difference (I-98 - I-1): {mean_diff:.3f} degC")
    print(f"Max absolute difference:      {max_abs:.3f} degC")
    print(f"Pearson correlation:          {corr:.3f}\n")

    mismatches = comp_df[comp_df["exceeds_threshold"]].copy()
    if not mismatches.empty:
        print("Examples exceeding threshold:")
        cols_to_show = ["timestamp", "TOBS.I-1",
                        "TOBS.I-98", "diff", "abs_diff"]
        print(mismatches[cols_to_show].head(12).to_string(index=False))
        print()

# -----------------------------
# Main: fetch, parse, compare
# -----------------------------


def main():
    url = build_wcis_url()
    print(f"[INFO] Fetching: {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    text = resp.text

    comp = compare_tobs_i1_vs_i98(text, threshold=THRESHOLD)
    print_summary(comp, threshold=THRESHOLD)

    # Optional: write CSV next to your repo folder
    # comp.to_csv("comparison_tobs_i1_vs_i98.csv", index=False)


if __name__ == "__main__":
    main()
