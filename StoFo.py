# live_option_chain.py
# Run: streamlit run StoFo.py

import streamlit as st
import pandas as pd
from datetime import date, datetime
from nsemine import fno

st.set_page_config(page_title="Live Option Chain", layout="wide")

st.title("📊 Live NSE Option Chain")
st.caption("Fetches live Call & Put data for any F&O stock")

# ── Stock Input ─────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    symbol = st.text_input("Enter Stock Symbol", value="RELIANCE", placeholder="e.g. RELIANCE, HDFCBANK, TCS").upper().strip()
with col2:
    st.write("")
    st.write("")
    refresh = st.button("🔄 Refresh")

if not symbol:
    st.stop()

# ── Fetch Expiries ──────────────────────────────────────────
@st.cache_data(ttl=300)
def get_expiries(sym):
    try:
        # only_expiry=True avoids an nsemine bug with fractional strikes (e.g. 87.5)
        return fno.get_stock_option_details(symbol=sym, only_expiry=True) or []
    except Exception as e:
        return []

expiries = get_expiries(symbol)
if not expiries:
    st.error(f"No option chain found for {symbol}. Make sure it is an F&O stock.")
    st.stop()

selected_expiry = st.selectbox(
    "Expiry Date",
    options=expiries,
    format_func=lambda d: d.strftime("%d-%b-%Y"),
    index=0
)

# ── Fetch Option Chain ──────────────────────────────────────
@st.cache_data(ttl=60)
def load_chain(sym, expiry):
    return fno.get_option_chain(symbol=sym, expiry_date=expiry)

with st.spinner(f"Loading {symbol} option chain..."):
    df = load_chain(symbol, selected_expiry)

if df is None or df.empty:
    st.warning("No data returned. Market may be closed or symbol invalid.")
    st.stop()

# ── Summary Metrics ─────────────────────────────────────────
spot = df["spot_price"].iloc[0]
total_ce_oi = df["ce_oi"].sum()
total_pe_oi = df["pe_oi"].sum()
pcr = total_pe_oi / total_ce_oi if total_ce_oi else 0

# Simple Max Pain approximation
df["pain"] = df["ce_oi"] * (df["strike_price"] - spot).clip(lower=0) + df["pe_oi"] * (spot - df["strike_price"]).clip(lower=0)
max_pain_strike = df.loc[df["pain"].idxmin(), "strike_price"]

st.subheader(f"{symbol} | Spot: ₹{spot:,.2f} | Expiry: {selected_expiry.strftime('%d %b %Y')}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Call OI", f"{total_ce_oi:,.0f}")
m2.metric("Total Put OI", f"{total_pe_oi:,.0f}")
m3.metric("PCR (OI)", f"{pcr:.2f}")
m4.metric("Max Pain (approx)", f"{max_pain_strike:,.0f}")

# ── Prepare Display Table ───────────────────────────────────
display = df[[
    "strike_price",
    "ce_oi", "ce_oi_change", "ce_volume", "ce_iv", "ce_ltp",
    "pe_ltp", "pe_iv", "pe_volume", "pe_oi_change", "pe_oi"
]].copy()

display.columns = [
    "Strike",
    "Call OI", "Call OI Δ", "Call Vol", "Call IV", "Call LTP",
    "Put LTP", "Put IV", "Put Vol", "Put OI Δ", "Put OI"
]

# Highlight ATM
atm_idx = (display["Strike"] - spot).abs().idxmin()
def highlight_atm(row):
    if row.name == atm_idx:
        return ["background-color: #1e3a5f"] * len(row)
    return [""] * len(row)

st.dataframe(
    display.style.apply(highlight_atm, axis=1).format({
        "Call OI": "{:,.0f}", "Call OI Δ": "{:+,.0f}", "Call Vol": "{:,.0f}",
        "Call IV": "{:.1f}", "Call LTP": "{:.2f}",
        "Put LTP": "{:.2f}", "Put IV": "{:.1f}", "Put Vol": "{:,.0f}",
        "Put OI Δ": "{:+,.0f}", "Put OI": "{:,.0f}"
    }),
    width="stretch",
    height=600
)

st.caption(f"Last updated: {datetime.now().strftime('%d %b %Y, %I:%M:%S %p IST')} | ATM strike highlighted")
st.info("Green/Red in OI Δ indicates buildup or unwinding. High Call OI often acts as resistance; high Put OI as support.")