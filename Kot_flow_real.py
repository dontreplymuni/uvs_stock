"""F&O Flow Live Board Dashboard
Real-time F&O Market Flow, Top Movers, and Option Bias Analysis
Supports Kotak Neo API authentication & live NSE/F&O market streaming.
"""

import time
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st

try:
    from neo_api_client import NeoAPI
except ImportError:
    NeoAPI = None

from nsemine import fno, nse

# Page configuration
st.set_page_config(
    page_title="F&O Flow Board · Live Market View",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for modern dark trading terminal aesthetic
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .header-bar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: linear-gradient(90deg, #0f172a 0%, #1e1b4b 100%);
        padding: 12px 20px;
        border-radius: 10px;
        margin-bottom: 18px;
        border: 1px solid #312e81;
    }
    .ist-time {
        font-family: 'Courier New', monospace;
        font-size: 1.15rem;
        font-weight: 700;
        color: #38bdf8;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ── IST Time Display Header ──────────────────────────────────
ist_zone = pytz.timezone("Asia/Kolkata")
current_ist = datetime.now(ist_zone).strftime("%d %b %Y | %I:%M:%S %p IST")

col_hdr1, col_hdr2 = st.columns([3, 1])
with col_hdr1:
    st.title("⚡ F&O Flow · Real-Time Market Board")
    st.caption("Live Derivative Bias · Open Interest Build-up · Top Movers")
with col_hdr2:
    st.markdown(
        f"""
        <div style="text-align: right; padding-top: 10px;">
            <span style="font-size: 0.85rem; color: #94a3b8;">Current Market Time</span><br/>
            <span class="ist-time">🕒 {current_ist}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Sidebar Configuration & Kotak Neo Login ──────────────────
with st.sidebar:
    st.header("⚙️ Settings & Connection")

    # Data Source Selection
    data_mode = st.radio(
        "Data Provider",
        ["NSE Live Data (Instant)", "Kotak Neo API + NSE"],
        index=0,
        help="Use NSE live data directly or connect your Kotak Neo Trade API session.",
    )

    auto_refresh = st.checkbox("Auto-refresh Dashboard", value=False)
    refresh_interval = st.slider(
        "Refresh Interval (seconds)",
        min_value=3,
        max_value=60,
        value=10,
        step=1,
        help="Auto-refresh period. Recommended: 5-15s to respect rate limits.",
    )

    num_movers = st.slider("Movers to analyze", min_value=6, max_value=25, value=12, step=1)

    st.markdown("---")
    st.subheader("🔐 Kotak Neo Login (Optional)")
    consumer_key = st.text_input(
        "Consumer Key",
        value="87afc2c6-0697-4ba9-bab5-336945bb451c",
        type="password",
        help="Obtained from Kotak Neo API Dashboard",
    )
    mobile = st.text_input("Mobile Number (+91)", value="+91", help="Registered mobile number")
    ucc = st.text_input("UCC (Client Code)", help="Your Neo Account UCC")
    totp = st.text_input("TOTP", type="password", help="Current 6-digit TOTP from Authenticator")
    mpin = st.text_input("MPIN", type="password", help="Your 6-digit Kotak Neo MPIN")

    login_col1, login_col2 = st.columns(2)
    with login_col1:
        login_btn = st.button("Connect", use_container_width=True)
    with login_col2:
        logout_btn = st.button("Logout", use_container_width=True)

if "client" not in st.session_state:
    st.session_state.client = None

if logout_btn:
    st.session_state.client = None
    st.sidebar.info("Kotak Neo disconnected.")

if login_btn and consumer_key and ucc and totp and mpin:
    if NeoAPI is None:
        st.sidebar.error("Kotak Neo SDK is not available in environment.")
    else:
        try:
            with st.spinner("Connecting to Kotak Neo Trade API..."):
                client = NeoAPI(
                    consumer_key=consumer_key.strip(),
                    environment="prod",
                    access_token=None,
                    neo_fin_key=None,
                )
                login_resp = client.totp_login(
                    mobile_number=mobile.strip(),
                    ucc=ucc.strip(),
                    totp=totp.strip(),
                )
                validate_resp = client.totp_validate(mpin=mpin.strip())
                st.session_state.client = client
                st.sidebar.success(" Kotak Neo Connected Successfully!")
        except Exception as e:
            st.sidebar.error(f"Login failed: {e}")

if st.session_state.client is not None:
    st.sidebar.success("🟢 Kotak Neo Session Active")
elif data_mode == "Kotak Neo API + NSE":
    st.sidebar.warning("⚠️ Kotak credentials not authenticated yet. Falling back to NSE engine.")


# ── Data Fetching Helpers ────────────────────────────────────
@st.cache_data(ttl=60)
def get_movers(limit=15):
    """Fetch top gainers and losers in the F&O segment."""
    try:
        gainers = nse.get_todays_gainers(key="FNO")
        losers = nse.get_todays_losers(key="FNO")
        return gainers.head(limit), losers.head(limit)
    except Exception as e:
        st.error(f"Error fetching top movers: {e}")
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=90)
def fetch_option_bias(symbol: str) -> dict:
    """Fetch option chain for nearest expiry and calculate derivative bias & OI build-up."""
    try:
        expiries = fno.get_stock_option_details(symbol=symbol, only_expiry=True) or []
        if not expiries:
            return None
        expiry = expiries[0]

        df = fno.get_option_chain(symbol=symbol, expiry_date=expiry)
        if df is None or df.empty:
            return None

        spot = float(df["spot_price"].iloc[0]) if "spot_price" in df.columns else 0.0
        ce_oi = float(df["ce_oi"].sum()) if "ce_oi" in df.columns else 0.0
        pe_oi = float(df["pe_oi"].sum()) if "pe_oi" in df.columns else 0.0
        ce_chg = float(df["ce_oi_change"].sum()) if "ce_oi_change" in df.columns else 0.0
        pe_chg = float(df["pe_oi_change"].sum()) if "pe_oi_change" in df.columns else 0.0

        pcr = round(pe_oi / ce_oi, 2) if ce_oi > 0 else 1.0

        # Flow score formula based on call vs put OI changes & PCR weighting
        total_oi = max(ce_oi + pe_oi, 1.0)
        score = (pe_chg - ce_chg) / total_oi * 100.0
        if pcr > 1.2:
            score += 0.5
        elif pcr < 0.7:
            score -= 0.5

        bias = "BULLISH" if score > 0 else "BEARISH"

        # Derivative Build-up Classification
        if pe_chg > 0 and ce_chg < 0:
            buildup = "Long Build-up"
        elif pe_chg < 0 and ce_chg < 0:
            buildup = "Short Covering"
        elif ce_chg > 0 and pe_chg < 0:
            buildup = "Short Build-up"
        elif ce_chg > 0 and pe_chg > 0:
            buildup = "Call & Put Addition"
        else:
            buildup = "Long Unwinding"

        return {
            "symbol": symbol,
            "spot": round(spot, 2),
            "pcr": pcr,
            "ce_oi": int(ce_oi),
            "pe_oi": int(pe_oi),
            "ce_oi_chg": int(ce_chg),
            "pe_oi_chg": int(pe_chg),
            "score": round(score, 2),
            "bias": bias,
            "buildup": buildup,
            "expiry": str(expiry),
        }
    except Exception:
        return None


# ── Action Buttons & Refresh ─────────────────────────────────
btn_col1, btn_col2, _ = st.columns([1, 1, 4])
with btn_col1:
    manual_refresh = st.button("🔄 Manual Refresh", use_container_width=True)
with btn_col2:
    clear_cache = st.button("🧹 Clear Cache", use_container_width=True)

if clear_cache:
    st.cache_data.clear()
    st.success("Cache cleared!")

# ── Data Pipeline Execution ──────────────────────────────────
placeholder = st.empty()

with placeholder.container():
    with st.spinner("Fetching live market movers and option chain metrics..."):
        gainers_df, losers_df = get_movers(limit=num_movers)

        symbols = []
        if not gainers_df.empty and "symbol" in gainers_df.columns:
            symbols.extend(list(gainers_df["symbol"]))
        if not losers_df.empty and "symbol" in losers_df.columns:
            symbols.extend(list(losers_df["symbol"]))

        # Remove duplicates while preserving ordering
        symbols = list(dict.fromkeys(symbols))[: (num_movers * 2)]

        records = []
        for sym in symbols:
            res = fetch_option_bias(sym)
            if res:
                # Merge price percentage change from movers table
                g_match = (
                    gainers_df[gainers_df["symbol"] == sym] if not gainers_df.empty else pd.DataFrame()
                )
                l_match = (
                    losers_df[losers_df["symbol"] == sym] if not losers_df.empty else pd.DataFrame()
                )

                if not g_match.empty and "changepct" in g_match.columns:
                    res["change_pct"] = round(float(g_match["changepct"].iloc[0]), 2)
                    res["mover"] = "🟢 Gainer"
                elif not l_match.empty and "changepct" in l_match.columns:
                    res["change_pct"] = round(float(l_match["changepct"].iloc[0]), 2)
                    res["mover"] = "🔴 Loser"
                else:
                    res["change_pct"] = 0.0
                    res["mover"] = "⚪ Neutral"

                records.append(res)

        df = pd.DataFrame(records)

    if df.empty:
        st.warning("⚠️ No derivative data returned. Markets might be closed or API rate limit reached.")
    else:
        # ── KPI Dashboard Cards ──────────────────────────────
        bullish_count = len(df[df["bias"] == "BULLISH"])
        bearish_count = len(df[df["bias"] == "BEARISH"])
        avg_pcr = round(df["pcr"].mean(), 2)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Movers Analyzed", len(df))
        with m2:
            st.metric("Bullish Bias Count", bullish_count, delta=f"{bullish_count} Stocks")
        with m3:
            st.metric("Bearish Bias Count", bearish_count, delta=f"-{bearish_count} Stocks", delta_color="inverse")
        with m4:
            st.metric("Average Flow PCR", avg_pcr)

        st.markdown("---")

        # ── Two Column Layout (Flow & Bias Analysis / Movers) ─
        col_flow, col_movers = st.columns([2.2, 1])

        with col_flow:
            st.subheader("📊 Bullish vs Bearish Bias Breakdown")
            c_bull, c_bear = st.columns(2)

            with c_bull:
                st.markdown("#### 🟢 Bullish Bias")
                bull_df = df[df["bias"] == "BULLISH"]
                if not bull_df.empty:
                    st.dataframe(
                        bull_df[["symbol", "mover", "change_pct", "pcr", "buildup"]].rename(
                            columns={
                                "symbol": "Stock",
                                "mover": "Type",
                                "change_pct": "Chg %",
                                "pcr": "PCR",
                                "buildup": "Build-up",
                            }
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.info("No stocks currently tagged with bullish bias.")

            with c_bear:
                st.markdown("#### 🔴 Bearish Bias")
                bear_df = df[df["bias"] == "BEARISH"]
                if not bear_df.empty:
                    st.dataframe(
                        bear_df[["symbol", "mover", "change_pct", "pcr", "buildup"]].rename(
                            columns={
                                "symbol": "Stock",
                                "mover": "Type",
                                "change_pct": "Chg %",
                                "pcr": "PCR",
                                "buildup": "Build-up",
                            }
                        ),
                        hide_index=True,
                        use_container_width=True,
                    )
                else:
                    st.info("No stocks currently tagged with bearish bias.")

            # ── Sankey Flow Diagram ──────────────────────────
            st.subheader("🔀 Market Flow Sankey Diagram")
            sankey_labels = ["Movers Pool"] + list(df["symbol"]) + ["BULLISH FLOW", "BEARISH FLOW"]
            source, target, value, link_colors = [], [], [], []

            bullish_node_idx = len(df) + 1
            bearish_node_idx = len(df) + 2

            for i, row in df.iterrows():
                vol_weight = abs(row["score"]) + 1.0
                # Source (Movers Pool -> Stock)
                source.append(0)
                target.append(i + 1)
                value.append(vol_weight)
                link_colors.append("rgba(148, 163, 184, 0.4)")

                # Target (Stock -> Bias Node)
                dest = bullish_node_idx if row["bias"] == "BULLISH" else bearish_node_idx
                source.append(i + 1)
                target.append(dest)
                value.append(vol_weight)
                link_colors.append(
                    "rgba(16, 185, 129, 0.6)" if row["bias"] == "BULLISH" else "rgba(239, 68, 68, 0.6)"
                )

            node_colors = (
                ["#334155"]
                + ["#10b981" if r["bias"] == "BULLISH" else "#ef4444" for _, r in df.iterrows()]
                + ["#059669", "#dc2626"]
            )

            fig = go.Figure(
                data=[
                    go.Sankey(
                        node=dict(
                            pad=15,
                            thickness=20,
                            line=dict(color="black", width=0.5),
                            label=sankey_labels,
                            color=node_colors,
                        ),
                        link=dict(
                            source=source,
                            target=target,
                            value=value,
                            color=link_colors,
                        ),
                    )
                ]
            )
            fig.update_layout(
                height=460,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#f8fafc", size=11),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_movers:
            st.subheader("📈 Top Gainers")
            if not gainers_df.empty:
                cols_to_show = [c for c in ["symbol", "changepct", "close"] if c in gainers_df.columns]
                st.dataframe(
                    gainers_df[cols_to_show].head(8).rename(
                        columns={"symbol": "Symbol", "changepct": "Chg %", "close": "LTP"}
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

            st.subheader("📉 Top Losers")
            if not losers_df.empty:
                cols_to_show = [c for c in ["symbol", "changepct", "close"] if c in losers_df.columns]
                st.dataframe(
                    losers_df[cols_to_show].head(8).rename(
                        columns={"symbol": "Symbol", "changepct": "Chg %", "close": "LTP"}
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

        st.markdown("---")
        st.subheader("📋 Comprehensive Flow & Option Bias Matrix")
        display_cols = [
            "symbol",
            "mover",
            "change_pct",
            "spot",
            "pcr",
            "ce_oi_chg",
            "pe_oi_chg",
            "buildup",
            "bias",
            "score",
            "expiry",
        ]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df.sort_values("change_pct", ascending=False)[available_cols],
            hide_index=True,
            use_container_width=True,
        )

# ── Auto-refresh Loop ────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()