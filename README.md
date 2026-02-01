# S&P 500 Share Price Scraper & Analyzer

A Streamlit web app that fetches all S&P 500 (VUSA ETF) holdings, downloads historical share price data from Yahoo Finance, and provides interactive charts and analytics for investment strategy research.

## Features

### Data
- Scrapes current S&P 500 constituent list from Wikipedia
- Downloads historical prices from Yahoo Finance (daily, weekly, monthly, or annual)
- Offline disk caching — data is saved locally after each fetch to avoid repeated API calls
- Export all data to Excel (.xlsx) with 5 sheets

### Analytics (15 tabs)

| Tab | Description |
|-----|-------------|
| **Top Performers** | Ranked table and bar chart of top N stocks by cumulative return |
| **Cumulative Returns** | Growth of $1 invested over time for selected stocks |
| **Price History** | Interactive price chart with optional normalization (start at 100) |
| **Drawdown Analysis** | Percentage decline from peak over time, max drawdown table |
| **Risk vs Return** | Scatter plot of annualized volatility vs return, colored by sector |
| **Sector Performance** | Average return by GICS sector, sector weight distribution |
| **Return Distribution** | Histogram of periodic returns vs S&P 500 average, with skewness/kurtosis |
| **Correlation Matrix** | Heatmap of pairwise return correlations |
| **Rolling Returns** | Rolling annualized return chart with configurable window |
| **All Holdings** | Full searchable table of all S&P 500 stocks with stats, filterable by sector |
| **Growth Simulator** | Simulate lump-sum investment growth (e.g. $10,000) across stocks and S&P 500 |
| **DCA Simulator** | Dollar-cost averaging simulation with total invested vs portfolio value |
| **Portfolio Builder** | Custom weighted portfolio vs S&P 500 benchmark comparison |
| **Stock Screener** | Filter stocks by min return, max drawdown, min Sharpe ratio, and sector |
| **Recovery Analysis** | Worst drawdown recovery times per stock, with scatter plot and not-recovered list |

## Setup

```bash
# Clone the repo
git clone https://github.com/erindhoxha88/data-scraper.git
cd data-scraper

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app opens at [http://localhost:8501](http://localhost:8501).

## Usage

1. Set parameters in the sidebar (years of history, data interval, top N)
2. Click **Fetch Data (API)** to download from Yahoo Finance (auto-saves to cache)
3. Or select a previously cached dataset and click **Load Cached Data** for offline use
4. Explore the 15 tabs
5. Export to Excel from the sidebar

## Project Structure

```
data-scraper/
  app.py             # Streamlit web interface (15 tabs + sidebar controls)
  scraper.py         # Core scraping and analysis logic (no UI code)
  requirements.txt   # Python dependencies
  cache/             # Auto-generated offline cache (parquet + JSON metadata)
```

## Requirements

- Python 3.10+
- Dependencies: pandas, yfinance, streamlit, plotly, numpy, scipy, openpyxl, lxml, html5lib
