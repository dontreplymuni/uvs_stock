# fno_flow_board.py
# Run: streamlit run flo_r.py

import streamlit as st
import pandas as pd
from datetime import datetime
from nsemine import nse, fno
import plotly.graph_objects as go

st.set_page_config(page_title="F&O Flow Board", layout="wide")

st.title("F&O Flow · Live Board")
st.caption("Daily top 15 gainers & losers · Option bias from nearest expiry")

# ── Fetch top gainers & losers ───────────────────────────────
@st.cache_data(ttl=120)
def get_movers():
    try:
        gainers = nse.get_todays_gainers(key="FNO")
        losers = nse.get_todays_losers(key="FNO")
        return gainers.head(15), losers.head(15)
    except Exception as e:
        st.error(f"Could not fetch movers: {e}")
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=180)
def fetch_bias(symbol: str) -> dict:
    try:
        # only_expiry=True avoids an nsemine bug with fractional strikes (e.g. 87.5)
        expiries = fno.get_stock_option_details(symbol=symbol, only_expiry=True) or []
        if not expiries:
            return None
        expiry = expiries[0]
        df = fno.get_option_chain(symbol=symbol, expiry_date=expiry)
        if df is None or df.empty:
            return None

        spot = df["spot_price"].iloc[0]
        ce_oi = df["ce_oi"].sum()
        pe_oi = df["pe_oi"].sum()
        ce_chg = df["ce_oi_change"].sum()
        pe_chg = df["pe_oi_change"].sum()
        pcr = pe_oi / ce_oi if ce_oi else 1

        score = (pe_chg - ce_chg) / max(ce_oi + pe_oi, 1) * 100
        if pcr > 1.1:
            score += 0.5
        elif pcr < 0.8:
            score -= 0.5

        bias = "BULLISH" if score > 0 else "BEARISH"
        buildup = (
            "Long Build-up" if pe_chg > 0 and ce_chg < 0 else
            "Short Covering" if pe_chg < 0 and ce_chg < 0 else
            "Short Build-up" if ce_chg > 0 and pe_chg < 0 else
            "Long Unwinding"
        )

        return {
            "symbol": symbol,
            "spot": round(spot, 2),
            "pcr": round(pcr, 2),
            "ce_oi_chg": int(ce_chg),
            "pe_oi_chg": int(pe_chg),
            "score": round(score, 2),
            "bias": bias,
            "buildup": buildup,
        }
    except Exception:
        return None

# ── Load ─────────────────────────────────────────────────────
if st.button("Refresh") or "data" not in st.session_state:
    with st.spinner("Fetching top movers and option chains..."):
        gainers_df, losers_df = get_movers()
        symbols = list(gainers_df["symbol"].head(15)) + list(losers_df["symbol"].head(15))
        symbols = list(dict.fromkeys(symbols))  # unique, preserve order

        results = []
        for sym in symbols:
            res = fetch_bias(sym)
            if res:
                # attach price change
                g_row = gainers_df[gainers_df["symbol"] == sym]
                l_row = losers_df[losers_df["symbol"] == sym]
                if not g_row.empty:
                    res["change_pct"] = g_row["changepct"].iloc[0]
                    res["mover"] = "Gainer"
                elif not l_row.empty:
                    res["change_pct"] = l_row["changepct"].iloc[0]
                    res["mover"] = "Loser"
                else:
                    res["change_pct"] = 0
                    res["mover"] = "-"
                results.append(res)

        st.session_state.data = pd.DataFrame(results)
        st.session_state.gainers = gainers_df
        st.session_state.losers = losers_df

df = st.session_state.get("data", pd.DataFrame())
gainers_df = st.session_state.get("gainers", pd.DataFrame())
losers_df = st.session_state.get("losers", pd.DataFrame())

if df.empty:
    st.warning("No data. Click Refresh.")
    st.stop()

# ── Layout ───────────────────────────────────────────────────
left, right = st.columns([2.2, 1])

with left:
    st.subheader("Flow Summary")
    bullish = df[df["bias"] == "BULLISH"]
    bearish = df[df["bias"] == "BEARISH"]

    c1, c2 = st.columns(2)
    with c1:
        st.metric("Bullish", len(bullish))
        if not bullish.empty:
            st.dataframe(
                bullish[["symbol", "mover", "change_pct", "pcr", "buildup"]].rename(
                    columns={"symbol": "Stock", "mover": "Type", "change_pct": "% Chg", "pcr": "PCR"}
                ),
                hide_index=True, width="stretch",
            )
    with c2:
        st.metric("Bearish", len(bearish))
        if not bearish.empty:
            st.dataframe(
                bearish[["symbol", "mover", "change_pct", "pcr", "buildup"]].rename(
                    columns={"symbol": "Stock", "mover": "Type", "change_pct": "% Chg", "pcr": "PCR"}
                ),
                hide_index=True, width="stretch",
            )

    # Sankey flow
    st.subheader("Bias Flow")
    labels = ["Movers"] + list(df["symbol"]) + ["BULLISH", "BEARISH"]
    source, target, value = [], [], []
    for i, row in df.iterrows():
        source.append(0)
        target.append(i + 1)
        value.append(abs(row["score"]) + 1)
        bias_node = len(df) + 1 if row["bias"] == "BULLISH" else len(df) + 2
        source.append(i + 1)
        target.append(bias_node)
        value.append(abs(row["score"]) + 1)

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            label=labels,
            color=["#1e293b"] + ["#10b981" if r["bias"]=="BULLISH" else "#ef4444" for _, r in df.iterrows()] + ["#10b981", "#ef4444"],
            pad=12,
        ),
        link=dict(source=source, target=target, value=value),
    )])
    fig.update_layout(height=480, margin=dict(l=5, r=5, t=5, b=5), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")

with right:
    st.subheader("Top Gainers")
    if not gainers_df.empty:
        st.dataframe(
            gainers_df[["symbol", "changepct", "close"]].head(10).rename(
                columns={"symbol": "Stock", "changepct": "%", "close": "LTP"}
            ),
            hide_index=True, width="stretch",
        )
    st.subheader("Top Losers")
    if not losers_df.empty:
        st.dataframe(
            losers_df[["symbol", "changepct", "close"]].head(10).rename(
                columns={"symbol": "Stock", "changepct": "%", "close": "LTP"}
            ),
            hide_index=True, width="stretch",
        )

st.divider()
st.subheader("Full Detail (Top Movers + Option Bias)")
st.dataframe(
    df.sort_values("change_pct", ascending=False)[
        ["symbol", "mover", "change_pct", "spot", "pcr", "ce_oi_chg", "pe_oi_chg", "buildup", "bias", "score"]
    ],
    hide_index=True, width="stretch",
)

st.caption(f"Updated: {datetime.now().strftime('%d %b %Y, %I:%M %p IST')} · Bias is a simple composite of OI change & PCR.")
