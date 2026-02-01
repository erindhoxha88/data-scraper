# Code Health & Bug Audit Report

## Summary

The application is functional and delivers value, but contains **1 systemic bug** that affects the correctness of all financial metrics when using non-monthly data intervals, along with several edge-case crashes and UX issues.

**Total issues found: 33** (across `scraper.py` and `app.py`)

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 3 | Silently wrong financial calculations |
| High | 7 | Runtime crashes or incorrect results under reachable conditions |
| Medium | 11 | UX failures, performance issues, corruption risks |
| Low | 12 | Edge cases, cosmetic, theoretical |

---

## Critical Issues (Fix Immediately)

### 1. All annualization formulas hardcode 12 periods/year

**Impact:** Every metric — annualized return, volatility, Sharpe ratio, CAGR, rolling returns — is **silently wrong** for Daily, Weekly, and Annual intervals. With daily data, annualized returns are underestimated by orders of magnitude. With annual data, they are wildly overstated.

**Root cause:** The number `12` is hardcoded in 8+ locations across both files:
- `ann_return = (1 + cum_ret) ** (12 / n_periods) - 1`
- `vol = returns_df[ticker].std() * np.sqrt(12)`
- `(1 + x).prod() ** (12 / window) - 1` (rolling returns)
- `n_years = len(growth_display) / 12` (growth simulator CAGR)

**Correct factors:** Daily=252, Weekly=52, Monthly=12, Annual=1

**Risk:** Users selecting Daily or Annual intervals receive plausible-looking but incorrect numbers, which could mislead investment decisions. This is the highest-priority fix.

---

## High Severity Issues

| # | Location | Issue |
|---|----------|-------|
| 2 | `get_top_performers`, `get_summary_stats` | `cumulative.iloc[-1]` crashes with `IndexError` if DataFrame is empty (single price row or all-NaN data) |
| 3 | `calculate_cumulative_returns` | Interior NaN values in returns silently truncate cumulative return series via `cumprod()`, producing wrong final values |
| 4 | `download_prices` | Single-ticker column handling assumes specific yfinance output format that varies across versions |
| 5 | `simulate_lump_sum` S&P 500 average | Equal-weight average of raw prices is not financially meaningful — a $400 stock dominates a $50 stock regardless of returns |
| 6 | Tab 13 `_port_stats` | Crashes with `IndexError` if portfolio return series is empty |
| 7 | Stale `top_n` | Changing the Top N slider without re-fetching silently does nothing — confusing UX |

---

## Medium Severity Issues

| # | Location | Issue |
|---|----------|-------|
| 8 | `save_to_cache` | Non-atomic writes — process interruption leaves cache corrupted |
| 9 | `load_from_cache` | No try/except for corrupted parquet/JSON files |
| 10 | `get_sp500_holdings` | Assumes Wikipedia table is always `tables[0]`; no network error handling |
| 11 | `build_portfolio_returns` | NaN returns for a ticker silently reduce the effective weight (returns understated) |
| 12 | Excel download button | Disappears on next Streamlit rerun before user can click it |
| 13 | Tab 15 `calculate_recovery_periods` | Recomputed on every single widget interaction (no caching), ~500 ticker iterations each time |
| 14 | Tab 14 Stock Screener | `KeyError` if `summary_df` is empty (no columns to filter on) |
| 15 | Rolling window slider | Max=60 is too low for daily data (1 year = 252 trading days) |
| 16 | `cache_options` variable | Referenced but never defined when no cached datasets exist (safe due to short-circuit, but fragile) |
| 17 | `calculate_drawdowns` | Division by zero if running max is 0 |
| 18 | Recovery period peak detection | Compares drawdown `== 0` which may fail due to floating-point precision |

---

## Low Severity Issues (12 total)

- Approximate leap year handling (`years * 365` instead of `365.25`)
- Cosmetic rounding in DCA simulator accumulation
- Progress callback defined but never passed to download function
- Missing explicit widget keys on some Streamlit widgets
- Theoretical KeyErrors on dataset switching
- Month-based arithmetic imprecise for daily data in recovery analysis
- `get_correlation_matrix` treats empty list `[]` as "all tickers" instead of "none"
- `export_to_excel` no graceful error if openpyxl missing (it's in requirements but not guarded)
- `build_portfolio_returns` silently drops unavailable tickers without warning
- `calculate_recovery_periods` uses calendar month diff (imprecise for daily/weekly data)
- Normalize checkbox in Price History tab missing explicit widget key
- Default multiselect values could theoretically reference absent tickers

---

## App Health Assessment

| Area | Rating | Notes |
|------|--------|-------|
| **Core functionality** | Good | Data fetching, caching, and tab rendering all work for the default monthly interval |
| **Calculation accuracy** | Poor for non-monthly | All metrics wrong for Daily/Weekly/Annual; correct for Monthly |
| **Error handling** | Weak | Missing guards for empty DataFrames, network failures, and corrupted cache |
| **Performance** | Acceptable | Recovery analysis runs on every rerun; daily 30-year data may be slow |
| **UX** | Good with gaps | Excel download button vanishes; top_n slider is misleading; progress bar non-functional |
| **Cache reliability** | Medium risk | Non-atomic writes; no corruption recovery |

---

## Recommended Fix Priority

1. **Pass interval annualization factor through all analytics functions** — fixes the critical calculation bug for all non-monthly intervals (Critical, 8+ locations)
2. **Add empty DataFrame guards** to `get_top_performers`, `get_summary_stats`, `_port_stats`, and screener tabs (High, prevents crashes)
3. **Fix S&P 500 average** to use normalized returns instead of raw price average (High, produces wrong investment simulation)
4. **Cache recovery analysis in session state** and add try/except to `load_from_cache` (Medium, performance + reliability)
5. **Store Excel bytes in session state** so the download button persists (Medium, UX)
6. **Recompute `top_perf_df` when `top_n` changes** without requiring a full re-fetch (High, UX)
