"""Unified Indian Markets Trading & Derivatives Terminal
Runs all individual trading apps in a seamless multi-page dashboard.
"""

import streamlit as st

# Configure multi-page navigation using Streamlit 1.36+ st.navigation
pages = {
    "⚡ Execution & Signals": [
        st.Page("vol_kotak_buy.py", title="F&O Decision & Order Board", icon="⚡", default=True),
    ],
    "📊 Market Flow & Momentum": [
        st.Page("Emotional_hack.py", title="Index Momentum (Rate of Change)", icon="🎯"),
        st.Page("Kot_flow_real.py", title="F&O Real-Time Flow Board", icon="📈"),
        st.Page("flo_r.py", title="Top F&O Movers & Bias", icon="🔥"),
    ],
    "🔍 Options & Institutional Analytics": [
        st.Page("StoFo.py", title="Live Stock Option Chain", icon="📊"),
        st.Page("exlimp.py", title="FII / DII Institutional Flows", icon="🏛️"),
    ],
}

pg = st.navigation(pages)
pg.run()
