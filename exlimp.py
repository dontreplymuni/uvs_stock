# fii_dii_dashboard.py
# Run with: streamlit run exlimp.py   (or simply: python exlimp.py)

import sys
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# Allow running via "python exlimp.py" by relaunching through Streamlit
if __name__ == "__main__":
    from streamlit import runtime
    if not runtime.exists():
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())

st.set_page_config(page_title="FII DII Dashboard", layout="wide")

st.title("📈 FII & DII Institutional Flow Dashboard")
st.caption("Data source: NSE India (Provisional cash market figures)")

# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_fii_dii():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/reports/fii-dii",
    }
    session = requests.Session()
    # First hit homepage to get cookies
    session.get("https://www.nseindia.com", headers=headers, timeout=15)
    # Then fetch FII/DII data
    resp = session.get("https://www.nseindia.com/api/fiidiiTradeReact", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return pd.DataFrame(data)

try:
    df = fetch_fii_dii()
except Exception as e:
    st.error(f"Failed to fetch data from NSE: {e}")
    st.stop()

# Clean & convert numbers
for col in ["buyValue", "sellValue", "netValue"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y")
df = df.sort_values("date", ascending=False)

# ─────────────────────────────────────────────────────────────
# Latest day summary
latest_date = df["date"].max()
latest = df[df["date"] == latest_date].set_index("category")

fii = latest.loc["FII/FPI"]
dii = latest.loc["DII"]

combined_net = fii["netValue"] + dii["netValue"]

st.subheader(f"Latest Session: {latest_date.strftime('%d %b %Y')}")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "FII / FPI Net",
        f"₹{fii['netValue']:,.2f} Cr",
        delta=f"{fii['netValue']:+,.0f}",
        delta_color="normal",
    )
    st.caption(f"Buy: ₹{fii['buyValue']:,.0f} Cr | Sell: ₹{fii['sellValue']:,.0f} Cr")

with col2:
    st.metric(
        "DII Net",
        f"₹{dii['netValue']:,.2f} Cr",
        delta=f"{dii['netValue']:+,.0f}",
        delta_color="normal",
    )
    st.caption(f"Buy: ₹{dii['buyValue']:,.0f} Cr | Sell: ₹{dii['sellValue']:,.0f} Cr")

with col3:
    st.metric(
        "Combined Net",
        f"₹{combined_net:,.2f} Cr",
        delta=f"{combined_net:+,.0f}",
        delta_color="normal",
    )
    st.caption("FII + DII")

# ─────────────────────────────────────────────────────────────
st.divider()

# Chart
chart_df = df.copy()
chart_df["category"] = chart_df["category"].replace({"FII/FPI": "FII", "DII": "DII"})

fig = px.bar(
    chart_df,
    x="date",
    y="netValue",
    color="category",
    barmode="group",
    title="Daily Net Institutional Flow (₹ Cr)",
    labels={"netValue": "Net (₹ Cr)", "date": "Date"},
    color_discrete_map={"FII": "#1f77b4", "DII": "#2ca02c"},
)
fig.update_layout(height=400, xaxis_tickangle=-45)
st.plotly_chart(fig, width="stretch")

# ─────────────────────────────────────────────────────────────
st.subheader("Recent Data")
display_df = df[["date", "category", "buyValue", "sellValue", "netValue"]].copy()
display_df.columns = ["Date", "Category", "Buy (₹ Cr)", "Sell (₹ Cr)", "Net (₹ Cr)"]
display_df["Date"] = display_df["Date"].dt.strftime("%d-%b-%Y")
st.dataframe(display_df, width="stretch", hide_index=True)

# ─────────────────────────────────────────────────────────────
st.info(
    "**Note:** This is **provisional** data published by NSE after market close "
    "(usually between 6–8 PM IST). It covers the cash market only. "
    "Final numbers from NSDL/CDSL may differ slightly."
)

st.caption(f"Last refreshed: {datetime.now().strftime('%d %b %Y, %I:%M %p IST')}")