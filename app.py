"""
VUSA ETF / S&P 500 Share Price Scraper & Analyzer
Streamlit web application.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats as scipy_stats

from scraper import (
    get_sp500_holdings,
    download_prices,
    calculate_returns,
    calculate_cumulative_returns,
    calculate_drawdowns,
    calculate_rolling_returns,
    get_top_performers,
    get_summary_stats,
    get_sector_performance,
    get_correlation_matrix,
    export_to_excel,
    save_to_cache,
    load_from_cache,
    list_cached_datasets,
    simulate_lump_sum,
    simulate_dca,
    build_portfolio_returns,
    calculate_recovery_periods,
)

st.set_page_config(
    page_title="S&P 500 Analyzer",
    page_icon="📈",
    layout="wide",
)

st.title("VUSA ETF / S&P 500 Share Price Analyzer")

# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.header("Parameters")

years = st.sidebar.slider("Years of history", min_value=1, max_value=30, value=20)

interval_map = {"Monthly": "1mo", "Weekly": "1wk", "Daily": "1d", "Annual": "1y"}
interval_label = st.sidebar.selectbox("Data interval", list(interval_map.keys()))
interval = interval_map[interval_label]

top_n = st.sidebar.slider("Top N performers", min_value=5, max_value=50, value=10)

fetch_clicked = st.sidebar.button("Fetch Data (API)", type="primary")

# ── Cache controls ───────────────────────────────────────────────────────────

st.sidebar.markdown("---")
st.sidebar.header("Offline Cache")

cached_datasets = list_cached_datasets()
if cached_datasets:
    cache_options = {
        f"{d['interval']} / {d['years']}y  ({d['tickers']} tickers, {d['fetched_at'][:10]})": d
        for d in cached_datasets
    }
    selected_cache = st.sidebar.selectbox(
        "Available cached datasets",
        options=["(none)"] + list(cache_options.keys()),
    )
    load_cache_clicked = st.sidebar.button("Load Cached Data")
else:
    st.sidebar.caption("No cached data yet. Fetch data once and it will be saved automatically.")
    selected_cache = "(none)"
    load_cache_clicked = False

# ── Session state ────────────────────────────────────────────────────────────

if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False


@st.cache_data(show_spinner=False)
def cached_get_holdings():
    return get_sp500_holdings()


@st.cache_data(show_spinner=False)
def cached_download_prices(_tickers, years, interval):
    """Wrapper to cache price downloads. _tickers prefixed with _ to skip hashing."""
    return download_prices(list(_tickers), years=years, interval=interval)


# ── Data fetching ────────────────────────────────────────────────────────────

def _run_analytics(prices_df, holdings_df, top_n):
    """Compute all derived analytics and store in session state."""
    with st.spinner("Calculating analytics..."):
        returns_df = calculate_returns(prices_df)
        cumulative_df = calculate_cumulative_returns(returns_df)
        drawdowns_df = calculate_drawdowns(prices_df)
        top_perf_df = get_top_performers(returns_df, holdings_df, n=top_n)
        summary_df = get_summary_stats(returns_df, holdings_df)
        sector_df = get_sector_performance(returns_df, holdings_df)

    st.session_state.holdings_df = holdings_df
    st.session_state.prices_df = prices_df
    st.session_state.returns_df = returns_df
    st.session_state.cumulative_df = cumulative_df
    st.session_state.drawdowns_df = drawdowns_df
    st.session_state.top_perf_df = top_perf_df
    st.session_state.summary_df = summary_df
    st.session_state.sector_df = sector_df
    st.session_state.failed = []
    st.session_state.data_loaded = True


# --- Load from cache ---
if load_cache_clicked and selected_cache != "(none)":
    meta = cache_options[selected_cache]
    cached = load_from_cache(meta["years"], meta["interval"])
    if cached is None:
        st.error("Cache files missing or corrupted.")
    else:
        prices_df, holdings_df, meta = cached
        st.sidebar.success(
            f"Loaded from cache: {meta['tickers']} tickers, fetched {meta['fetched_at'][:10]}"
        )
        _run_analytics(prices_df, holdings_df, top_n)

# --- Fresh fetch from API ---
if fetch_clicked:
    with st.spinner("Fetching S&P 500 holdings from Wikipedia..."):
        holdings_df = cached_get_holdings()
    st.sidebar.success(f"Loaded {len(holdings_df)} holdings")

    tickers = holdings_df["Symbol"].tolist()

    progress_bar = st.progress(0, text="Downloading price data...")
    status_text = st.empty()

    def update_progress(current, total):
        pct = current / total if total > 0 else 0
        progress_bar.progress(pct, text=f"Downloading batch {current}/{total}...")

    prices_df, failed = cached_download_prices(tuple(tickers), years, interval)

    progress_bar.progress(1.0, text="Download complete!")

    if failed:
        st.sidebar.warning(f"{len(failed)} tickers failed to download")

    if prices_df.empty:
        st.error("No price data was downloaded. Please try again.")
        st.stop()

    # Auto-save to disk cache
    save_to_cache(prices_df, holdings_df, years, interval)
    st.sidebar.success("Data saved to offline cache.")

    st.session_state.failed = failed
    _run_analytics(prices_df, holdings_df, top_n)

# ── Main content ─────────────────────────────────────────────────────────────

if not st.session_state.data_loaded:
    st.info("Configure parameters in the sidebar and click **Fetch Data** to begin.")
    st.stop()

# Retrieve from session state
holdings_df = st.session_state.holdings_df
prices_df = st.session_state.prices_df
returns_df = st.session_state.returns_df
cumulative_df = st.session_state.cumulative_df
drawdowns_df = st.session_state.drawdowns_df
top_perf_df = st.session_state.top_perf_df
summary_df = st.session_state.summary_df
sector_df = st.session_state.sector_df
failed = st.session_state.failed

all_tickers = sorted(prices_df.columns.tolist())
top_tickers = top_perf_df["Ticker"].tolist()

# ── Tabs ─────────────────────────────────────────────────────────────────────

tabs = st.tabs([
    "Top Performers",
    "Cumulative Returns",
    "Price History",
    "Drawdown Analysis",
    "Risk vs Return",
    "Sector Performance",
    "Return Distribution",
    "Correlation Matrix",
    "Rolling Returns",
    "All Holdings",
    "Growth Simulator",
    "DCA Simulator",
    "Portfolio Builder",
    "Stock Screener",
    "Recovery Analysis",
])

# ── Tab 1: Top Performers ───────────────────────────────────────────────────

with tabs[0]:
    st.header("Top Performers")
    st.dataframe(top_perf_df, use_container_width=True, hide_index=True)

    fig = px.bar(
        top_perf_df.iloc[::-1],
        x="Cumulative Return (%)",
        y="Ticker",
        orientation="h",
        color="Sector",
        hover_data=["Company", "Annualized Return (%)", "Sharpe Ratio"],
        title=f"Top {len(top_perf_df)} Stocks by Cumulative Return",
    )
    fig.update_layout(height=max(400, len(top_perf_df) * 30))
    st.plotly_chart(fig, use_container_width=True)

# ── Tab 2: Cumulative Returns ───────────────────────────────────────────────

with tabs[1]:
    st.header("Cumulative Returns (Growth of $1)")

    selected_cum = st.multiselect(
        "Select tickers",
        options=all_tickers,
        default=top_tickers[:10],
        key="cum_select",
    )

    if selected_cum:
        plot_data = cumulative_df[selected_cum].dropna(how="all")
        fig = px.line(
            plot_data,
            title="Cumulative Returns Over Time",
            labels={"value": "Cumulative Return", "variable": "Ticker"},
        )
        fig.update_layout(hovermode="x unified", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Select at least one ticker.")

# ── Tab 3: Price History ────────────────────────────────────────────────────

with tabs[2]:
    st.header("Price History")

    selected_price = st.multiselect(
        "Select tickers",
        options=all_tickers,
        default=top_tickers[:5],
        key="price_select",
    )

    normalize = st.checkbox("Normalize (start at 100)", value=False)

    if selected_price:
        plot_prices = prices_df[selected_price].dropna(how="all")
        if normalize:
            first_valid = plot_prices.apply(lambda col: col.dropna().iloc[0] if col.dropna().shape[0] > 0 else np.nan)
            plot_prices = (plot_prices / first_valid) * 100

        fig = px.line(
            plot_prices,
            title="Adjusted Close Prices" + (" (Normalized)" if normalize else ""),
            labels={"value": "Price" if not normalize else "Normalized Price (100=start)", "variable": "Ticker"},
        )
        fig.update_layout(hovermode="x unified", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Select at least one ticker.")

# ── Tab 4: Drawdown Analysis ────────────────────────────────────────────────

with tabs[3]:
    st.header("Drawdown Analysis")

    selected_dd = st.multiselect(
        "Select tickers",
        options=all_tickers,
        default=top_tickers[:5],
        key="dd_select",
    )

    if selected_dd:
        plot_dd = drawdowns_df[selected_dd].dropna(how="all") * 100
        fig = px.line(
            plot_dd,
            title="Drawdown from Peak (%)",
            labels={"value": "Drawdown (%)", "variable": "Ticker"},
        )
        fig.update_layout(hovermode="x unified", height=600)
        st.plotly_chart(fig, use_container_width=True)

        # Max drawdown table
        max_dd = drawdowns_df[selected_dd].min() * 100
        dd_table = pd.DataFrame({
            "Ticker": max_dd.index,
            "Max Drawdown (%)": max_dd.values.round(2),
        }).sort_values("Max Drawdown (%)").reset_index(drop=True)
        st.subheader("Max Drawdown per Ticker")
        st.dataframe(dd_table, use_container_width=True, hide_index=True)
    else:
        st.warning("Select at least one ticker.")

# ── Tab 5: Risk vs Return ───────────────────────────────────────────────────

with tabs[4]:
    st.header("Risk vs Return")

    if not summary_df.empty:
        fig = px.scatter(
            summary_df,
            x="Volatility (%)",
            y="Annualized Return (%)",
            color="Sector",
            hover_data=["Ticker", "Company", "Sharpe Ratio"],
            title="Risk vs Return (Annualized)",
        )
        fig.update_layout(height=700)
        fig.update_traces(marker=dict(size=8, opacity=0.7))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No summary data available.")

# ── Tab 6: Sector Performance ───────────────────────────────────────────────

with tabs[5]:
    st.header("Sector Performance")

    if not sector_df.empty:
        col1, col2 = st.columns(2)

        with col1:
            fig = px.bar(
                sector_df.sort_values("Avg Cumulative Return (%)"),
                x="Avg Cumulative Return (%)",
                y="Sector",
                orientation="h",
                title="Average Cumulative Return by Sector",
                color="Avg Cumulative Return (%)",
                color_continuous_scale="RdYlGn",
            )
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.pie(
                sector_df,
                values="# Stocks",
                names="Sector",
                title="Sector Weight Distribution (# of Stocks)",
            )
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Sector Statistics")
        st.dataframe(sector_df, use_container_width=True, hide_index=True)
    else:
        st.warning("No sector data available.")

# ── Tab 7: Return Distribution ──────────────────────────────────────────────

with tabs[6]:
    st.header("Return Distribution")

    selected_dist = st.selectbox(
        "Select a ticker",
        options=all_tickers,
        index=all_tickers.index(top_tickers[0]) if top_tickers and top_tickers[0] in all_tickers else 0,
        key="dist_select",
    )

    if selected_dist and selected_dist in returns_df.columns:
        ticker_returns = returns_df[selected_dist].dropna() * 100
        market_avg = returns_df.mean(axis=1).dropna() * 100

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=ticker_returns,
            name=selected_dist,
            opacity=0.7,
            nbinsx=50,
        ))
        fig.add_trace(go.Histogram(
            x=market_avg,
            name="S&P 500 Average",
            opacity=0.5,
            nbinsx=50,
        ))
        fig.update_layout(
            barmode="overlay",
            title=f"Return Distribution: {selected_dist} vs S&P 500 Average",
            xaxis_title="Return (%)",
            yaxis_title="Frequency",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Statistics
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Mean (%)", f"{ticker_returns.mean():.2f}")
        col2.metric("Median (%)", f"{ticker_returns.median():.2f}")
        col3.metric("Std Dev (%)", f"{ticker_returns.std():.2f}")
        col4.metric("Skewness", f"{scipy_stats.skew(ticker_returns):.2f}")
        col5.metric("Kurtosis", f"{scipy_stats.kurtosis(ticker_returns):.2f}")
    else:
        st.warning("Select a valid ticker.")

# ── Tab 8: Correlation Matrix ───────────────────────────────────────────────

with tabs[7]:
    st.header("Correlation Matrix")

    selected_corr = st.multiselect(
        "Select tickers",
        options=all_tickers,
        default=top_tickers[:10],
        key="corr_select",
    )

    if selected_corr and len(selected_corr) >= 2:
        corr_matrix = get_correlation_matrix(returns_df, selected_corr)

        fig = px.imshow(
            corr_matrix,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="Pairwise Return Correlations",
        )
        fig.update_layout(height=max(500, len(selected_corr) * 40))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Select at least 2 tickers.")

# ── Tab 9: Rolling Returns ──────────────────────────────────────────────────

with tabs[8]:
    st.header("Rolling Returns")

    rolling_window = st.slider("Rolling window (periods)", min_value=3, max_value=60, value=12, key="rolling_window")

    selected_roll = st.multiselect(
        "Select tickers",
        options=all_tickers,
        default=top_tickers[:5],
        key="roll_select",
    )

    if selected_roll:
        rolling_df = calculate_rolling_returns(prices_df[selected_roll], window=rolling_window) * 100

        fig = px.line(
            rolling_df.dropna(how="all"),
            title=f"Rolling {rolling_window}-Period Annualized Return (%)",
            labels={"value": "Annualized Return (%)", "variable": "Ticker"},
        )
        fig.update_layout(hovermode="x unified", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Select at least one ticker.")

# ── Tab 10: All Holdings ────────────────────────────────────────────────────

with tabs[9]:
    st.header("All Holdings")

    sectors = ["All"] + sorted(summary_df["Sector"].unique().tolist())
    selected_sector = st.selectbox("Filter by sector", sectors, key="holdings_sector")

    display_df = summary_df.copy()
    if selected_sector != "All":
        display_df = display_df[display_df["Sector"] == selected_sector]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=600,
    )
    st.caption(f"Showing {len(display_df)} of {len(summary_df)} stocks")

# ── Tab 11: Growth Simulator ─────────────────────────────────────────────────

with tabs[10]:
    st.header("Investment Growth Simulator")
    st.caption("See how a lump-sum investment would have grown over time.")

    col_a, col_b = st.columns(2)
    with col_a:
        initial_investment = st.number_input(
            "Initial investment ($)", min_value=100, max_value=10_000_000,
            value=10000, step=1000, key="growth_amount",
        )
    with col_b:
        growth_tickers_input = st.multiselect(
            "Compare stocks (leave empty for S&P 500 average only)",
            options=all_tickers,
            default=[],
            key="growth_tickers",
        )

    sim_tickers = ["_SP500_AVG_"] + growth_tickers_input
    growth_df = simulate_lump_sum(prices_df, sim_tickers, initial_investment)

    if not growth_df.empty:
        # Rename _SP500_AVG_ for display
        display_cols = {c: ("S&P 500 Avg" if c == "_SP500_AVG_" else c) for c in growth_df.columns}
        growth_display = growth_df.rename(columns=display_cols)

        fig = px.line(
            growth_display,
            title=f"Growth of ${initial_investment:,.0f} Lump-Sum Investment",
            labels={"value": "Portfolio Value ($)", "variable": "Investment"},
        )
        fig.update_layout(hovermode="x unified", height=600)
        fig.add_hline(y=initial_investment, line_dash="dash", line_color="gray",
                      annotation_text=f"Initial: ${initial_investment:,.0f}")
        st.plotly_chart(fig, use_container_width=True)

        # Summary table
        final_vals = growth_display.iloc[-1]
        summary_rows = []
        for name, val in final_vals.items():
            total_return = ((val / initial_investment) - 1) * 100
            n_years = len(growth_display) / 12  # approximate for monthly data
            cagr = ((val / initial_investment) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
            summary_rows.append({
                "Investment": name,
                "Final Value ($)": f"{val:,.2f}",
                "Total Return (%)": f"{total_return:,.2f}",
                "CAGR (%)": f"{cagr:.2f}",
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    else:
        st.warning("No data available for simulation.")

# ── Tab 12: DCA Simulator ───────────────────────────────────────────────────

with tabs[11]:
    st.header("Dollar-Cost Averaging Simulator")
    st.caption("Simulate investing a fixed amount every period instead of a lump sum.")

    col_a, col_b = st.columns(2)
    with col_a:
        dca_amount = st.number_input(
            "Amount per period ($)", min_value=10, max_value=1_000_000,
            value=500, step=100, key="dca_amount",
        )
    with col_b:
        dca_ticker = st.selectbox(
            "Invest in",
            options=["S&P 500 Average"] + all_tickers,
            key="dca_ticker",
        )

    actual_ticker = "_SP500_AVG_" if dca_ticker == "S&P 500 Average" else dca_ticker
    dca_df = simulate_dca(prices_df, actual_ticker, periodic_amount=dca_amount)

    if not dca_df.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dca_df.index, y=dca_df["Total Invested"],
            name="Total Invested", line=dict(dash="dash"),
        ))
        fig.add_trace(go.Scatter(
            x=dca_df.index, y=dca_df["Portfolio Value"],
            name="Portfolio Value", fill="tonexty",
        ))
        fig.update_layout(
            title=f"DCA ${dca_amount:,.0f}/period into {dca_ticker}",
            yaxis_title="Value ($)",
            hovermode="x unified",
            height=600,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Key metrics
        final = dca_df.iloc[-1]
        profit = final["Portfolio Value"] - final["Total Invested"]
        ret_pct = (profit / final["Total Invested"]) * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Invested", f"${final['Total Invested']:,.2f}")
        col2.metric("Portfolio Value", f"${final['Portfolio Value']:,.2f}")
        col3.metric("Profit / Loss", f"${profit:,.2f}")
        col4.metric("Return on Invested", f"{ret_pct:.2f}%")

        with st.expander("View detailed DCA schedule"):
            st.dataframe(dca_df.reset_index(), use_container_width=True, hide_index=True)
    else:
        st.warning("No data available for this ticker.")

# ── Tab 13: Portfolio Builder ────────────────────────────────────────────────

with tabs[12]:
    st.header("Portfolio Builder")
    st.caption("Construct a custom portfolio and compare it against the S&P 500 average.")

    port_tickers = st.multiselect(
        "Select stocks for your portfolio",
        options=all_tickers,
        default=top_tickers[:3] if len(top_tickers) >= 3 else top_tickers,
        key="port_tickers",
    )

    if port_tickers:
        st.subheader("Set weights (%)")
        equal_w = 100.0 / len(port_tickers)
        weights_pct = {}
        cols = st.columns(min(len(port_tickers), 4))
        for i, ticker in enumerate(port_tickers):
            with cols[i % len(cols)]:
                weights_pct[ticker] = st.number_input(
                    ticker, min_value=0.0, max_value=100.0,
                    value=round(equal_w, 1), step=1.0, key=f"pw_{ticker}",
                )

        total_weight = sum(weights_pct.values())
        if total_weight == 0:
            st.warning("Total weight is 0. Adjust your weights.")
        else:
            if abs(total_weight - 100) > 0.1:
                st.info(f"Weights sum to {total_weight:.1f}%. They will be normalized to 100%.")

            weights = {t: w / 100.0 for t, w in weights_pct.items()}
            port_returns = build_portfolio_returns(returns_df, weights)
            sp500_returns = returns_df.mean(axis=1)

            port_cum = calculate_cumulative_returns(port_returns)
            sp500_cum = calculate_cumulative_returns(sp500_returns)

            compare_df = pd.DataFrame({
                "Your Portfolio": (1 + port_cum) * 10000,
                "S&P 500 Average": (1 + sp500_cum) * 10000,
            })

            fig = px.line(
                compare_df,
                title="Portfolio vs S&P 500 Average (Growth of $10,000)",
                labels={"value": "Value ($)", "variable": ""},
            )
            fig.update_layout(hovermode="x unified", height=600)
            st.plotly_chart(fig, use_container_width=True)

            # Stats comparison
            def _port_stats(ret_series, label):
                cum = ((1 + ret_series).cumprod() - 1).iloc[-1]
                n_periods = ret_series.dropna().shape[0]
                ann_ret = (1 + cum) ** (12 / n_periods) - 1 if n_periods > 0 else 0
                vol = ret_series.std() * np.sqrt(12)
                sharpe = ann_ret / vol if vol > 0 else 0
                wealth = (1 + ret_series).cumprod()
                max_dd = ((wealth / wealth.cummax()) - 1).min()
                return {
                    "": label,
                    "Cumulative Return (%)": round(cum * 100, 2),
                    "Annualized Return (%)": round(ann_ret * 100, 2),
                    "Volatility (%)": round(vol * 100, 2),
                    "Sharpe Ratio": round(sharpe, 2),
                    "Max Drawdown (%)": round(max_dd * 100, 2),
                }

            stats_table = pd.DataFrame([
                _port_stats(port_returns, "Your Portfolio"),
                _port_stats(sp500_returns, "S&P 500 Average"),
            ])
            st.dataframe(stats_table, use_container_width=True, hide_index=True)
    else:
        st.warning("Select at least one stock.")

# ── Tab 14: Stock Screener ───────────────────────────────────────────────────

with tabs[13]:
    st.header("Stock Screener")
    st.caption("Filter stocks by performance and risk criteria.")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        min_return = st.number_input(
            "Min Cumulative Return (%)", value=0.0, step=10.0, key="scr_min_ret",
        )
    with col_b:
        max_drawdown = st.number_input(
            "Max Drawdown (%) (e.g. -50)", value=-100.0, step=5.0, key="scr_max_dd",
        )
    with col_c:
        min_sharpe = st.number_input(
            "Min Sharpe Ratio", value=0.0, step=0.1, key="scr_min_sharpe",
        )
    with col_d:
        scr_sectors = st.multiselect(
            "Sectors",
            options=sorted(summary_df["Sector"].unique().tolist()),
            default=[],
            key="scr_sectors",
        )

    filtered = summary_df.copy()
    filtered = filtered[filtered["Cumulative Return (%)"] >= min_return]
    filtered = filtered[filtered["Max Drawdown (%)"] >= max_drawdown]
    filtered = filtered[filtered["Sharpe Ratio"] >= min_sharpe]
    if scr_sectors:
        filtered = filtered[filtered["Sector"].isin(scr_sectors)]

    st.subheader(f"Results: {len(filtered)} stocks match")
    st.dataframe(filtered, use_container_width=True, hide_index=True, height=500)

    if not filtered.empty:
        fig = px.scatter(
            filtered,
            x="Volatility (%)",
            y="Annualized Return (%)",
            color="Sector",
            hover_data=["Ticker", "Company", "Sharpe Ratio", "Max Drawdown (%)"],
            title="Screened Stocks: Risk vs Return",
        )
        fig.update_traces(marker=dict(size=9, opacity=0.8))
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

# ── Tab 15: Recovery Analysis ────────────────────────────────────────────────

with tabs[14]:
    st.header("Recovery Analysis")
    st.caption("How long did each stock take to recover from its worst drawdown?")

    recovery_df = calculate_recovery_periods(prices_df, holdings_df)

    if not recovery_df.empty:
        # Sector filter
        rec_sectors = ["All"] + sorted(recovery_df["Sector"].unique().tolist())
        rec_sector = st.selectbox("Filter by sector", rec_sectors, key="rec_sector")
        rec_display = recovery_df.copy()
        if rec_sector != "All":
            rec_display = rec_display[rec_display["Sector"] == rec_sector]

        st.dataframe(rec_display, use_container_width=True, hide_index=True, height=500)

        # Chart: recovery months vs drawdown depth
        chart_df = rec_display.copy()
        chart_df["Recovery (months) num"] = pd.to_numeric(chart_df["Recovery (months)"], errors="coerce")
        chart_recovered = chart_df.dropna(subset=["Recovery (months) num"])

        if not chart_recovered.empty:
            fig = px.scatter(
                chart_recovered,
                x="Max Drawdown (%)",
                y="Recovery (months) num",
                color="Sector",
                hover_data=["Ticker", "Company", "Peak Date", "Trough Date", "Recovery Date"],
                title="Drawdown Depth vs Recovery Time",
                labels={"Recovery (months) num": "Recovery (months)"},
            )
            fig.update_traces(marker=dict(size=8, opacity=0.7))
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        not_recovered = rec_display[rec_display["Recovery Date"] == "Not recovered"]
        if not not_recovered.empty:
            st.subheader(f"Not Yet Recovered ({len(not_recovered)} stocks)")
            st.dataframe(not_recovered[["Ticker", "Company", "Sector", "Max Drawdown (%)", "Peak Date", "Trough Date"]],
                         use_container_width=True, hide_index=True)
    else:
        st.warning("No recovery data available.")

# ── Download section ─────────────────────────────────────────────────────────

st.sidebar.markdown("---")
st.sidebar.header("Export")

if st.sidebar.button("Generate Excel File"):
    with st.spinner("Generating Excel..."):
        excel_bytes = export_to_excel(
            holdings_df, prices_df, returns_df, top_perf_df, summary_df
        )
    st.sidebar.download_button(
        label="Download Excel",
        data=excel_bytes,
        file_name="sp500_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
