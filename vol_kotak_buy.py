# fno_decision_dashboard.py
# Run: streamlit run vol_kotak_buy.py

import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
import plotly.graph_objects as go
import time

try:
    from neo_api_client import NeoAPI
except ImportError:
    NeoAPI = None

from nsemine import nse, fno

st.set_page_config(page_title="F&O Decision Board", layout="wide", page_icon="⚡")

# ── Header & IST Time ─────────────────────────────────────────
ist = pytz.timezone("Asia/Kolkata")
current_ist = datetime.now(ist).strftime("%d %b %Y, %I:%M:%S %p IST")

hdr_col1, hdr_col2 = st.columns([3, 1])
with hdr_col1:
    st.title("⚡ F&O Decision Board")
    st.caption("Live Buy/Sell Signals · Derivative Flow · Order Execution (Kotak Neo)")
with hdr_col2:
    st.markdown(
        f"""
        <div style="text-align: right; padding-top: 10px;">
            <span style="font-size: 0.85rem; color: #94a3b8;">Market Time</span><br/>
            <span style="font-family: monospace; font-size: 1.15rem; font-weight: bold; color: #38bdf8;">🕒 {current_ist}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Execution Settings")
    
    # Auto-refresh Controls
    auto_refresh = st.checkbox("Auto-refresh Data", value=False)
    refresh_seconds = st.slider("Refresh Interval (seconds)", min_value=5, max_value=60, value=15, step=1)
    
    st.divider()
    st.header("🔐 Kotak Neo Connection")
    consumer_key = st.text_input("Consumer Key", value="87afc2c6-0697-4ba9-bab5-336945bb451c", type="password")
    mobile = st.text_input("Mobile (+91...)")
    ucc = st.text_input("UCC")
    totp = st.text_input("TOTP", type="password")
    mpin = st.text_input("MPIN", type="password")
    
    col_lgn, col_lgo = st.columns(2)
    with col_lgn:
        login_clicked = st.button("Login", use_container_width=True)
    with col_lgo:
        logout_clicked = st.button("Logout", use_container_width=True)
        
    if logout_clicked:
        st.session_state.client = None
        st.info("Logged out.")

    if login_clicked:
        if NeoAPI is None:
            st.error("NeoAPI client library is not available.")
        elif not (consumer_key and ucc and totp and mpin):
            st.warning("Please fill in Consumer Key, UCC, TOTP, and MPIN.")
        else:
            try:
                client = NeoAPI(consumer_key=consumer_key.strip(), environment="prod")
                client.totp_login(mobile_number=mobile.strip(), ucc=ucc.strip(), totp=totp.strip())
                client.totp_validate(mpin=mpin.strip())
                st.session_state.client = client
                st.success("Successfully logged in to Kotak Neo!")
            except Exception as e:
                st.error(f"Login failed: {e}")

    st.divider()
    st.subheader("🛒 Order Defaults")
    default_qty = st.number_input("Default Quantity", min_value=1, value=1)
    product = st.selectbox("Product Segment", ["MIS", "NRML", "CNC"])
    order_type = st.selectbox("Order Type", ["MKT", "L"])
    limit_price = st.number_input("Limit Price (if L)", min_value=0.0, value=0.0, step=0.05)

client = st.session_state.get("client")
if client:
    st.sidebar.success("🟢 Kotak Neo Trading Session Active")
else:
    st.sidebar.info("ℹ️ Login above to enable direct 1-click order execution.")

# ── Data Helpers ─────────────────────────────────────────────
@st.cache_data(ttl=30)
def get_movers():
    try:
        g = nse.get_todays_gainers(key="FNO").head(8)
        l = nse.get_todays_losers(key="FNO").head(8)
        return g, l
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=45)
def get_bias_nse(symbol: str) -> dict:
    """Fallback high-speed calculation using NSE Option Chain."""
    try:
        expiries = fno.get_stock_option_details(symbol=symbol, only_expiry=True) or []
        if not expiries:
            return None
        expiry = expiries[0]
        chain = fno.get_option_chain(symbol=symbol, expiry_date=expiry)
        if chain is None or chain.empty:
            return None

        ce_oi = float(chain["ce_oi"].sum()) if "ce_oi" in chain.columns else 0.0
        pe_oi = float(chain["pe_oi"].sum()) if "pe_oi" in chain.columns else 0.0
        ce_chg = float(chain["ce_oi_change"].sum()) if "ce_oi_change" in chain.columns else 0.0
        pe_chg = float(chain["pe_oi_change"].sum()) if "pe_oi_change" in chain.columns else 0.0

        pcr = round(pe_oi / ce_oi, 2) if ce_oi > 0 else 1.0
        score = (pe_chg - ce_chg) / max(ce_oi + pe_oi, 1.0) * 100.0
        if pcr > 1.2:
            score += 0.5
        elif pcr < 0.7:
            score -= 0.5

        bias = "BULLISH" if score > 0 else "BEARISH"
        action = "BUY" if score > 0.5 else ("SELL" if score < -0.5 else "HOLD")
        return {
            "symbol": symbol,
            "bias": bias,
            "action": action,
            "score": round(score, 2),
            "pcr": pcr,
            "source": "NSE",
        }
    except Exception:
        return None

def get_bias(underlying: str, exchange: str = "nse_fo") -> dict:
    """Fetch bias using Kotak Neo client if active, otherwise fallback to NSE."""
    if client is not None:
        try:
            chain = client.option_chain(
                exchange=exchange,
                underlying=underlying,
                instrument_type="option",
                count=30
            )
            if chain and "data" in chain:
                data = chain["data"]
                calls = data.get("call", [])
                puts = data.get("put", [])

                ce_vol = sum(float(c.get("quote", {}).get("volume", 0) or 0) for c in calls)
                pe_vol = sum(float(p.get("quote", {}).get("volume", 0) or 0) for p in puts)
                ce_oi = sum(float(c.get("quote", {}).get("oi", 0) or 0) for c in calls)
                pe_oi = sum(float(p.get("quote", {}).get("oi", 0) or 0) for p in puts)
                ce_chg = sum(float(c.get("quote", {}).get("oiChange", 0) or 0) for c in calls)
                pe_chg = sum(float(p.get("quote", {}).get("oiChange", 0) or 0) for p in puts)

                pcr = round(pe_oi / ce_oi, 2) if ce_oi else 1.0
                vol_ratio = pe_vol / ce_vol if ce_vol else 1.0
                score = (pe_chg - ce_chg) / max(ce_oi + pe_oi, 1.0) * 100.0 + (vol_ratio - 1.0) * 2.0

                bias = "BULLISH" if score > 0 else "BEARISH"
                action = "BUY" if score > 0.5 else ("SELL" if score < -0.5 else "HOLD")
                return {
                    "symbol": underlying,
                    "bias": bias,
                    "action": action,
                    "score": round(score, 2),
                    "pcr": pcr,
                    "source": "Kotak Neo",
                }
        except Exception:
            pass

    # Fallback to NSE for stock symbols
    return get_bias_nse(underlying)

def place_order(symbol: str, side: str, quantity: int, product_type: str, otype: str, price: float):
    if not client:
        return {"error": "Kotak Neo is not logged in. Please log in via sidebar first."}
    try:
        trading_symbol = f"{symbol}-EQ" if not symbol.startswith(("NIFTY", "BANK", "SENSEX")) else symbol
        exch = "nse_cm" if "-EQ" in trading_symbol else "nse_fo"
        resp = client.place_order(
            exchange_segment=exch,
            product=product_type,
            price=str(price) if otype == "L" and price > 0 else "0",
            order_type=otype,
            quantity=str(quantity),
            validity="DAY",
            trading_symbol=trading_symbol,
            transaction_type="B" if side == "BUY" else "S",
        )
        return resp
    except Exception as e:
        return {"error": str(e)}

# ── Dashboard Layout ─────────────────────────────────────────
top_act1, top_act2, _ = st.columns([1, 1, 4])
with top_act1:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
with top_act2:
    if st.button("🧹 Clear State", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

placeholder = st.empty()

with placeholder.container():
    with st.spinner("Analyzing market momentum and derivative signals..."):
        gainers_df, losers_df = get_movers()
        stock_symbols = []
        if not gainers_df.empty and "symbol" in gainers_df.columns:
            stock_symbols.extend(list(gainers_df["symbol"].head(6)))
        if not losers_df.empty and "symbol" in losers_df.columns:
            stock_symbols.extend(list(losers_df["symbol"].head(6)))
        stock_symbols = list(dict.fromkeys(stock_symbols))

        instruments = [
            ("NIFTY", "nse_fo"),
            ("BANKNIFTY", "nse_fo"),
            ("SENSEX", "bse_fo"),
            ("CRUDEOIL", "mcx_fo"),
            ("GOLD", "mcx_fo")
        ]

        results = []
        for sym, exch in instruments:
            b = get_bias(sym, exch)
            if b:
                b["type"] = "Index/Commodity"
                results.append(b)

        for sym in stock_symbols:
            b = get_bias(sym)
            if b:
                b["type"] = "Stock"
                results.append(b)

        df = pd.DataFrame(results)

    if not df.empty:
        # KPI Row
        buys = df[df["action"] == "BUY"]
        sells = df[df["action"] == "SELL"]
        holds = df[df["action"] == "HOLD"]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Signals Generated", len(df))
        k2.metric("🟢 BUY Signals", len(buys))
        k3.metric("🔴 SELL Signals", len(sells))
        k4.metric("⚪ Neutral / HOLD", len(holds))

        st.markdown("---")

        st.subheader("🎯 Actionable Signals — Click to Confirm & Execute")
        active_signals = df[df["action"].isin(["BUY", "SELL"])].head(10)
        
        if active_signals.empty:
            st.info("No strong Buy/Sell signals at this moment. Market is currently range-bound.")
        else:
            for _, row in active_signals.iterrows():
                key = f"confirm_{row['symbol']}_{row['action']}"
                cols = st.columns([2.5, 1, 1.2, 1.8])
                with cols[0]:
                    color = "🟢" if row["action"] == "BUY" else "🔴"
                    st.markdown(f"### {color} **{row['symbol']}**")
                    st.caption(f"{row['type']} · Action: **{row['action']}** · Score: `{row['score']}`")
                with cols[1]:
                    st.metric("PCR", row['pcr'])
                with cols[2]:
                    if st.button("⚡ Prepare", key=f"prep_{row['symbol']}"):
                        st.session_state[key] = True
                with cols[3]:
                    if st.session_state.get(key):
                        st.warning(f"Confirm {row['action']} {default_qty} {row['symbol']}?")
                        conf_col, cancel_col = st.columns(2)
                        with conf_col:
                            if st.button("Confirm", key=f"go_{row['symbol']}"):
                                if client is None:
                                    st.error("Please login to Kotak Neo first.")
                                else:
                                    res = place_order(row["symbol"], row["action"], default_qty, product, order_type, limit_price)
                                    if "error" in res:
                                        st.error(str(res["error"]))
                                    else:
                                        st.success(f"Order Placed: {res}")
                                st.session_state[key] = False
                        with cancel_col:
                            if st.button("Cancel", key=f"no_{row['symbol']}"):
                                st.session_state[key] = False

        st.markdown("---")

        # Visual Bias Score Chart
        st.subheader("📊 Bias Score Distribution")
        fig = go.Figure(go.Bar(
            x=df["symbol"],
            y=df["score"],
            marker_color=["#10b981" if s > 0 else "#ef4444" for s in df["score"]],
            text=df["action"],
            textposition="outside",
        ))
        fig.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#f8fafc")
        )
        st.plotly_chart(fig, use_container_width=True)

        # Zones
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🟢 BUY Zone")
            if not buys.empty:
                st.dataframe(buys[["symbol", "type", "score", "pcr", "source"]], hide_index=True, use_container_width=True)
            else:
                st.info("No symbols in BUY zone.")
        with c2:
            st.subheader("🔴 SELL Zone")
            if not sells.empty:
                st.dataframe(sells[["symbol", "type", "score", "pcr", "source"]], hide_index=True, use_container_width=True)
            else:
                st.info("No symbols in SELL zone.")
    else:
        st.warning("⚠️ No data available from NSE/Kotak. Markets might be closed or endpoints throttling.")

# ── Auto-refresh ─────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()