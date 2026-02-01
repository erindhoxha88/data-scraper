"""
Core scraping and analysis logic for VUSA ETF / S&P 500 share price analysis.
No UI code - pure data functions.
"""

import json
import os
import time
import io
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent / "cache"


# ── Disk cache helpers ───────────────────────────────────────────────────────

def _cache_key(years, interval):
    """Build a filename-safe cache key from parameters."""
    return f"prices_{years}y_{interval}"


def save_to_cache(prices_df, holdings_df, years, interval):
    """Persist price data and holdings to disk so they can be reloaded offline."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = _cache_key(years, interval)

    prices_df.to_parquet(CACHE_DIR / f"{key}.parquet")
    holdings_df.to_parquet(CACHE_DIR / "holdings.parquet")

    meta = {
        "years": years,
        "interval": interval,
        "tickers": len(prices_df.columns),
        "rows": len(prices_df),
        "fetched_at": datetime.now().isoformat(),
    }
    with open(CACHE_DIR / f"{key}_meta.json", "w") as f:
        json.dump(meta, f, indent=2)


def load_from_cache(years, interval):
    """Load previously cached data. Returns (prices_df, holdings_df, meta) or None."""
    key = _cache_key(years, interval)
    prices_path = CACHE_DIR / f"{key}.parquet"
    holdings_path = CACHE_DIR / "holdings.parquet"
    meta_path = CACHE_DIR / f"{key}_meta.json"

    if not prices_path.exists() or not holdings_path.exists() or not meta_path.exists():
        return None

    prices_df = pd.read_parquet(prices_path)
    holdings_df = pd.read_parquet(holdings_path)
    with open(meta_path) as f:
        meta = json.load(f)

    return prices_df, holdings_df, meta


def list_cached_datasets():
    """Return list of available cached datasets with their metadata."""
    if not CACHE_DIR.exists():
        return []
    datasets = []
    for meta_file in sorted(CACHE_DIR.glob("prices_*_meta.json")):
        with open(meta_file) as f:
            meta = json.load(f)
        datasets.append(meta)
    return datasets


def get_sp500_holdings():
    """Scrape S&P 500 constituent list from Wikipedia.

    Returns:
        DataFrame with columns: Symbol, Security, GICS Sector, GICS Sub-Industry,
        Headquarters Location, Date Added, CIK, Founded
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urlopen(req).read()
    tables = pd.read_html(io.StringIO(html.decode("utf-8")))
    df = tables[0]
    # Fix tickers that use dots on Wikipedia but Yahoo uses hyphens
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
    return df


def download_prices(tickers, years=20, interval="1mo", progress_callback=None):
    """Download adjusted close prices from Yahoo Finance in batches.

    Args:
        tickers: list of ticker symbols
        years: number of years of history
        interval: '1d', '1wk', '1mo', or '1y'
        progress_callback: optional callable(current_batch, total_batches) for progress updates

    Returns:
        (DataFrame of adjusted close prices, list of failed tickers)
    """
    # Yahoo Finance doesn't support '1y' interval directly.
    # Download monthly data and resample to year-end close.
    resample_annual = interval == "1y"
    yf_interval = "1mo" if resample_annual else interval

    end = datetime.now()
    start = end - timedelta(days=years * 365)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    batch_size = 50
    all_data = {}
    failed_tickers = []
    batches = [tickers[i : i + batch_size] for i in range(0, len(tickers), batch_size)]
    total_batches = len(batches)

    for batch_idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(batch_idx, total_batches)

        try:
            batch_str = " ".join(batch)
            data = yf.download(
                batch_str,
                start=start_str,
                end=end_str,
                interval=yf_interval,
                auto_adjust=True,
                threads=True,
            )

            if data.empty:
                failed_tickers.extend(batch)
                continue

            # yf.download returns MultiIndex columns when multiple tickers
            if isinstance(data.columns, pd.MultiIndex):
                close = data["Close"]
            else:
                # Single ticker case
                close = data[["Close"]]
                close.columns = batch[:1]

            for col in close.columns:
                if close[col].notna().sum() > 0:
                    all_data[col] = close[col]
                else:
                    failed_tickers.append(col)

        except Exception:
            failed_tickers.extend(batch)

        if batch_idx < total_batches - 1:
            time.sleep(2)

    if progress_callback:
        progress_callback(total_batches, total_batches)

    if not all_data:
        return pd.DataFrame(), failed_tickers

    prices_df = pd.DataFrame(all_data)
    prices_df.index = pd.to_datetime(prices_df.index)
    prices_df = prices_df.sort_index()

    if resample_annual:
        prices_df = prices_df.resample("YE").last().dropna(how="all")

    return prices_df, failed_tickers


def calculate_returns(prices_df):
    """Calculate periodic returns using pct_change.

    Returns:
        DataFrame of returns (same shape as input, first row NaN)
    """
    return prices_df.pct_change()


def calculate_cumulative_returns(returns_df):
    """Calculate cumulative return series (growth of $1).

    Returns:
        DataFrame where each value = cumulative return from start
    """
    return (1 + returns_df).cumprod() - 1


def calculate_drawdowns(prices_df):
    """Calculate drawdown from running peak for each ticker.

    Returns:
        DataFrame of drawdowns (negative values = decline from peak)
    """
    running_max = prices_df.cummax()
    drawdowns = (prices_df / running_max) - 1
    return drawdowns


def calculate_rolling_returns(prices_df, window=12):
    """Calculate rolling annualized returns.

    Args:
        prices_df: adjusted close prices
        window: rolling window in periods (e.g., 12 for 12-month rolling on monthly data)

    Returns:
        DataFrame of rolling annualized returns
    """
    rolling = prices_df.pct_change().rolling(window=window).apply(
        lambda x: (1 + x).prod() ** (12 / window) - 1 if len(x) == window else np.nan,
        raw=False,
    )
    return rolling


def get_top_performers(returns_df, holdings_df, n=10):
    """Rank stocks by cumulative return.

    Returns:
        DataFrame with top N performers including ticker, company, sector, cumulative return
    """
    cumulative = calculate_cumulative_returns(returns_df)
    final_returns = cumulative.iloc[-1].dropna().sort_values(ascending=False)

    top_tickers = final_returns.head(n).index.tolist()

    records = []
    for ticker in top_tickers:
        cum_ret = final_returns[ticker]
        match = holdings_df[holdings_df["Symbol"] == ticker]
        company = match["Security"].values[0] if len(match) > 0 else "N/A"
        sector = match["GICS Sector"].values[0] if len(match) > 0 else "N/A"

        # Annualized return
        n_periods = returns_df[ticker].dropna().shape[0]
        if n_periods > 0:
            ann_return = (1 + cum_ret) ** (12 / n_periods) - 1
        else:
            ann_return = 0

        # Volatility (annualized)
        vol = returns_df[ticker].std() * np.sqrt(12)

        # Sharpe ratio (assuming 0 risk-free rate for simplicity)
        sharpe = ann_return / vol if vol > 0 else 0

        records.append({
            "Ticker": ticker,
            "Company": company,
            "Sector": sector,
            "Cumulative Return (%)": round(cum_ret * 100, 2),
            "Annualized Return (%)": round(ann_return * 100, 2),
            "Volatility (%)": round(vol * 100, 2),
            "Sharpe Ratio": round(sharpe, 2),
        })

    return pd.DataFrame(records)


def get_summary_stats(returns_df, holdings_df):
    """Calculate summary statistics for all tickers.

    Returns:
        DataFrame with cumulative return, annualized return, volatility,
        Sharpe ratio, max drawdown per ticker
    """
    cumulative = calculate_cumulative_returns(returns_df)
    final_returns = cumulative.iloc[-1].dropna()

    records = []
    for ticker in final_returns.index:
        cum_ret = final_returns[ticker]
        match = holdings_df[holdings_df["Symbol"] == ticker]
        company = match["Security"].values[0] if len(match) > 0 else "N/A"
        sector = match["GICS Sector"].values[0] if len(match) > 0 else "N/A"

        n_periods = returns_df[ticker].dropna().shape[0]
        if n_periods > 0:
            ann_return = (1 + cum_ret) ** (12 / n_periods) - 1
        else:
            ann_return = 0

        vol = returns_df[ticker].std() * np.sqrt(12)
        sharpe = ann_return / vol if vol > 0 else 0

        # Max drawdown - calculate from cumulative returns series
        cum_series = cumulative[ticker].dropna()
        if len(cum_series) > 0:
            wealth = 1 + cum_series
            running_max = wealth.cummax()
            dd = (wealth / running_max) - 1
            max_dd = dd.min()
        else:
            max_dd = 0

        records.append({
            "Ticker": ticker,
            "Company": company,
            "Sector": sector,
            "Cumulative Return (%)": round(cum_ret * 100, 2),
            "Annualized Return (%)": round(ann_return * 100, 2),
            "Volatility (%)": round(vol * 100, 2),
            "Sharpe Ratio": round(sharpe, 2),
            "Max Drawdown (%)": round(max_dd * 100, 2),
        })

    df = pd.DataFrame(records)
    df = df.sort_values("Cumulative Return (%)", ascending=False).reset_index(drop=True)
    return df


def get_sector_performance(returns_df, holdings_df):
    """Calculate average return and stats by GICS sector.

    Returns:
        DataFrame with sector-level aggregated statistics
    """
    cumulative = calculate_cumulative_returns(returns_df)
    final_returns = cumulative.iloc[-1].dropna()

    records = []
    for ticker in final_returns.index:
        match = holdings_df[holdings_df["Symbol"] == ticker]
        if len(match) == 0:
            continue
        sector = match["GICS Sector"].values[0]
        cum_ret = final_returns[ticker]
        vol = returns_df[ticker].std() * np.sqrt(12)
        records.append({
            "Sector": sector,
            "Cumulative Return (%)": cum_ret * 100,
            "Volatility (%)": vol * 100,
        })

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame()

    sector_stats = df.groupby("Sector").agg(
        **{
            "Avg Cumulative Return (%)": ("Cumulative Return (%)", "mean"),
            "Avg Volatility (%)": ("Volatility (%)", "mean"),
            "# Stocks": ("Cumulative Return (%)", "count"),
        }
    ).round(2).sort_values("Avg Cumulative Return (%)", ascending=False).reset_index()

    return sector_stats


def get_correlation_matrix(returns_df, tickers=None):
    """Calculate pairwise return correlations.

    Args:
        returns_df: periodic returns DataFrame
        tickers: optional list of tickers to include (defaults to all)

    Returns:
        Correlation matrix DataFrame
    """
    if tickers:
        available = [t for t in tickers if t in returns_df.columns]
        subset = returns_df[available]
    else:
        subset = returns_df

    return subset.corr()


def simulate_lump_sum(prices_df, tickers, initial_investment=10000):
    """Simulate growth of a lump-sum investment over time.

    Args:
        prices_df: adjusted close prices
        tickers: list of tickers to simulate (use None for S&P 500 equal-weight avg)
        initial_investment: starting dollar amount

    Returns:
        DataFrame with portfolio value over time for each ticker
    """
    results = {}
    for ticker in tickers:
        if ticker == "_SP500_AVG_":
            series = prices_df.mean(axis=1).dropna()
        elif ticker in prices_df.columns:
            series = prices_df[ticker].dropna()
        else:
            continue
        if len(series) < 2:
            continue
        normalized = series / series.iloc[0]
        results[ticker] = normalized * initial_investment
    return pd.DataFrame(results)


def simulate_dca(prices_df, ticker, periodic_amount=500):
    """Simulate dollar-cost averaging into a single stock or the S&P 500 average.

    Invests a fixed dollar amount each period (row in prices_df).

    Args:
        prices_df: adjusted close prices
        ticker: ticker symbol, or '_SP500_AVG_' for equal-weight average
        periodic_amount: dollar amount invested each period

    Returns:
        DataFrame with columns: Date, Price, Shares Bought, Total Shares,
        Total Invested, Portfolio Value
    """
    if ticker == "_SP500_AVG_":
        price_series = prices_df.mean(axis=1).dropna()
    elif ticker in prices_df.columns:
        price_series = prices_df[ticker].dropna()
    else:
        return pd.DataFrame()

    records = []
    total_shares = 0.0
    total_invested = 0.0

    for date, price in price_series.items():
        if price <= 0 or np.isnan(price):
            continue
        shares_bought = periodic_amount / price
        total_shares += shares_bought
        total_invested += periodic_amount
        portfolio_value = total_shares * price
        records.append({
            "Date": date,
            "Price": round(price, 2),
            "Shares Bought": round(shares_bought, 4),
            "Total Shares": round(total_shares, 4),
            "Total Invested": round(total_invested, 2),
            "Portfolio Value": round(portfolio_value, 2),
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
    return df


def build_portfolio_returns(returns_df, weights):
    """Build a weighted portfolio return series.

    Args:
        returns_df: periodic returns DataFrame
        weights: dict of {ticker: weight} where weights sum to 1.0

    Returns:
        Series of portfolio returns
    """
    available = {t: w for t, w in weights.items() if t in returns_df.columns}
    if not available:
        return pd.Series(dtype=float)
    # Renormalize weights to sum to 1
    total_w = sum(available.values())
    if total_w == 0:
        return pd.Series(dtype=float)
    tickers = list(available.keys())
    w = np.array([available[t] / total_w for t in tickers])
    port_returns = (returns_df[tickers] * w).sum(axis=1)
    return port_returns


def calculate_recovery_periods(prices_df, holdings_df):
    """For each stock, find the worst drawdown and how long recovery took.

    Returns:
        DataFrame with: Ticker, Company, Sector, Peak Date, Trough Date,
        Recovery Date, Drawdown (%), Decline (months), Recovery (months), Total (months)
    """
    drawdowns = calculate_drawdowns(prices_df)
    records = []

    for ticker in prices_df.columns:
        dd = drawdowns[ticker].dropna()
        if len(dd) < 2:
            continue
        # Find trough (worst drawdown point)
        trough_idx = dd.idxmin()
        trough_val = dd[trough_idx]
        if trough_val >= 0:
            continue  # no drawdown

        # Find peak before trough (last time dd == 0 before trough)
        before_trough = dd.loc[:trough_idx]
        peaks = before_trough[before_trough == 0]
        if len(peaks) == 0:
            peak_date = dd.index[0]
        else:
            peak_date = peaks.index[-1]

        # Find recovery after trough (first time dd == 0 after trough)
        after_trough = dd.loc[trough_idx:]
        recoveries = after_trough[after_trough >= 0]
        if len(recoveries) == 0:
            recovery_date = None
            recovery_months = None
            total_months = None
        else:
            recovery_date = recoveries.index[0]
            recovery_months = (recovery_date.year - trough_idx.year) * 12 + (recovery_date.month - trough_idx.month)
            total_months = (recovery_date.year - peak_date.year) * 12 + (recovery_date.month - peak_date.month)

        decline_months = (trough_idx.year - peak_date.year) * 12 + (trough_idx.month - peak_date.month)

        match = holdings_df[holdings_df["Symbol"] == ticker]
        company = match["Security"].values[0] if len(match) > 0 else "N/A"
        sector = match["GICS Sector"].values[0] if len(match) > 0 else "N/A"

        records.append({
            "Ticker": ticker,
            "Company": company,
            "Sector": sector,
            "Peak Date": peak_date.strftime("%Y-%m-%d"),
            "Trough Date": trough_idx.strftime("%Y-%m-%d"),
            "Recovery Date": recovery_date.strftime("%Y-%m-%d") if recovery_date else "Not recovered",
            "Max Drawdown (%)": round(trough_val * 100, 2),
            "Decline (months)": decline_months,
            "Recovery (months)": recovery_months if recovery_months is not None else "N/A",
            "Total (months)": total_months if total_months is not None else "N/A",
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("Max Drawdown (%)").reset_index(drop=True)
    return df


def export_to_excel(holdings_df, prices_df, returns_df, top_performers_df, summary_df):
    """Write all data to an in-memory Excel workbook.

    Returns:
        BytesIO object containing the Excel file
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        holdings_df.to_excel(writer, sheet_name="Holdings", index=False)
        prices_df.to_excel(writer, sheet_name="Prices")
        returns_df.to_excel(writer, sheet_name="Returns")
        top_performers_df.to_excel(writer, sheet_name="Top Performers", index=False)
        summary_df.to_excel(writer, sheet_name="Summary Stats", index=False)
    output.seek(0)
    return output
