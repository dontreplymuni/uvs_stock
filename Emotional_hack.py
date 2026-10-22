# index_roc_dashboard.py
# Run: streamlit run index_roc_dashboard.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from neo_api_client import NeoAPI
import plotly.graph_objects as go
import time

st.set_page_config(page_title="Index Rate of Change", layout="wide")

ist = pytz.timezone("Asia/Kolkata")
st.markdown(f"### 🕒 {datetime.now(ist).strftime('%d %b %Y, %I:%M:%S %p IST')}")
st.title("Index Rate of Change Dashboard")
st.caption("Filter & plot minutes where Nifty / Sensex moved by your chosen points")

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.header("Kotak Neo Login")
    consumer_key = st.text_input("Consumer Key", value="87afc2c6-0697-4ba9-bab5-336945bb451c", type="password")
    mobile = st.text_input("Mobile (+91...)")
    ucc = st.text_input("UCC")
    totp = st.text_input("TOTP", type="password")
    mpin = st.text_input("MPIN", type="password")
    if st.button("Login"):
        try:
            client = NeoAPI(consumer_key=consumer_key, environment="prod")
            client.totp_login(mobile_number=mobile, ucc=ucc, totp=totp)
            client.totp_validate(mpin=mpin)
            st.session_state.client = client
            st.success("Logged in")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("Thresholds (points per minute)")
    nifty_thresh = st.number_input("Nifty 50 threshold", min_value=1, value=10, step=1)
    sensex_thresh = st.number_input("Sensex threshold", min_value=1, value=40, step=1)
    lookback_mins = st.slider("Lookback (minutes)", 30, 180, 60)
    st.divider()
    st.subheader("Auto-Refresh")
    auto_refresh = st.checkbox("Enable Auto-Refresh", value=False)
    refresh_seconds = st.slider("Refresh Interval (seconds)", min_value=3, max_value=60, value=10, step=1)


client = st.session_state.get("client")
if not client:
    st.info("Login via sidebar to load data.")
    st.stop()

# Index Instrument Token map for Kotak Neo
INDEX_TOKENS = {
    "NIFTY": "26000",   # Nifty 50 Cash index token on NSE
    "SENSEX": "1",      # BSE Sensex token on BSE
}

# ── Fetch 1-minute candles ───────────────────────────────────
def fetch_1min(symbol: str, exchange: str, minutes: int) -> pd.DataFrame:
    try:
        end = datetime.now(ist)
        start = end - timedelta(minutes=minutes)
        token = INDEX_TOKENS.get(symbol.upper(), symbol)
        data = client.historical_data(
            instrument_token=token,
            exchange_segment=exchange,
            from_date=start.strftime("%Y-%m-%d"),
            to_date=end.strftime("%Y-%m-%d"),
            interval="1minute",
        )
        if not data or "data" not in data:
            return pd.DataFrame()
        df = pd.DataFrame(data["data"])
        if df.empty:
            return df
        df["datetime"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("datetime")
        df["change"] = df["close"].diff()
        df["abs_change"] = df["change"].abs()
        return df
    except Exception as e:
        st.warning(f"{symbol}: {e}")
        return pd.DataFrame()

# ── Main ─────────────────────────────────────────────────────
placeholder = st.empty()

with placeholder.container():
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"Nifty 50  (≥ {nifty_thresh} pts/min)")
        nifty_df = fetch_1min("NIFTY", "nse_cm", lookback_mins)
        if not nifty_df.empty:
            filtered = nifty_df[nifty_df["abs_change"] >= nifty_thresh]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=nifty_df["datetime"], y=nifty_df["close"],
                mode="lines", name="Price", line=dict(color="#64748b")
            ))
            if not filtered.empty:
                fig.add_trace(go.Scatter(
                    x=filtered["datetime"], y=filtered["close"],
                    mode="markers", name=f"≥ {nifty_thresh} pts",
                    marker=dict(size=10, color="#ef4444" if filtered["change"].mean() < 0 else "#10b981")
                ))
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                filtered[["datetime", "close", "change"]].tail(20).rename(columns={"change": "Pts"}),
                hide_index=True, use_container_width=True
            )
        else:
            st.info("No Nifty data (check instrument token / market hours)")

    with col2:
        st.subheader(f"Sensex  (≥ {sensex_thresh} pts/min)")
        sensex_df = fetch_1min("SENSEX", "bse_cm", lookback_mins)
        if not sensex_df.empty:
            filtered = sensex_df[sensex_df["abs_change"] >= sensex_thresh]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=sensex_df["datetime"], y=sensex_df["close"],
                mode="lines", name="Price", line=dict(color="#64748b")
            ))
            if not filtered.empty:
                fig.add_trace(go.Scatter(
                    x=filtered["datetime"], y=filtered["close"],
                    mode="markers", name=f"≥ {sensex_thresh} pts",
                    marker=dict(size=10, color="#ef4444" if filtered["change"].mean() < 0 else "#10b981")
                ))
            fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                filtered[["datetime", "close", "change"]].tail(20).rename(columns={"change": "Pts"}),
                hide_index=True, use_container_width=True
            )
        else:
            st.info("No Sensex data")

    st.caption("Red/green markers = minutes that crossed your point threshold. Adjust thresholds in the sidebar.")

if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()