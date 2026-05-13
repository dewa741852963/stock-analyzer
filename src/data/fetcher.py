import yfinance as yf
import pandas as pd

PERIODS = {
    "1個月": "1mo",
    "3個月": "3mo",
    "6個月": "6mo",
    "1年": "1y",
    "2年": "2y",
}

def build_symbol(symbol: str, market: str) -> str:
    symbol = symbol.upper().strip()
    if market == "台股" and not symbol.endswith((".TW", ".TWO")):
        return symbol + ".TW"
    return symbol

def fetch_stock_data(symbol: str, market: str, period_label: str) -> dict:
    ticker_sym = build_symbol(symbol, market)
    period = PERIODS.get(period_label, "6mo")

    ticker = yf.Ticker(ticker_sym)
    hist = ticker.history(period=period)

    if hist.empty:
        raise ValueError(f"找不到股票資料：{ticker_sym}")

    # Remove timezone for compatibility
    if hasattr(hist.index, "tz") and hist.index.tz is not None:
        hist.index = hist.index.tz_localize(None)

    _add_indicators(hist)

    info = {}
    try:
        info = ticker.info or {}
    except Exception:
        pass

    return {"symbol": ticker_sym, "history": hist, "info": info}


def _add_indicators(hist: pd.DataFrame):
    import ta as ta_lib
    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]

    hist["RSI_14"] = ta_lib.momentum.RSIIndicator(close, window=14).rsi()

    macd_ind = ta_lib.trend.MACD(close)
    hist["MACD_12_26_9"] = macd_ind.macd()
    hist["MACDs_12_26_9"] = macd_ind.macd_signal()
    hist["MACDh_12_26_9"] = macd_ind.macd_diff()

    hist["SMA_20"] = ta_lib.trend.SMAIndicator(close, window=20).sma_indicator()
    hist["SMA_50"] = ta_lib.trend.SMAIndicator(close, window=50).sma_indicator()

    bb = ta_lib.volatility.BollingerBands(close, window=20)
    hist["BBU_20_2.0"] = bb.bollinger_hband()
    hist["BBL_20_2.0"] = bb.bollinger_lband()



def find_col(hist: pd.DataFrame, prefix: str):
    for c in hist.columns:
        if c.startswith(prefix):
            return c
    return None


INTERVAL_MAP = {
    "分時": ("1d",  "1m"),
    "日線": (None,  "1d"),   # period from PERIODS, interval daily
    "週線": ("2y",  "1wk"),
    "月線": ("5y",  "1mo"),
}


def fetch_interval_data(symbol: str, interval_label: str, period_label: str = "6個月") -> dict:
    """依時間週期取得 OHLCV，用於切換 分時/日線/週線/月線。"""
    period_override, interval = INTERVAL_MAP[interval_label]
    period = period_override or PERIODS.get(period_label, "6mo")

    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval)

    if hist.empty:
        raise ValueError(f"無資料：{symbol} ({interval_label})")

    if hasattr(hist.index, "tz") and hist.index.tz is not None:
        hist.index = hist.index.tz_localize(None)

    # 日線以外不計算技術指標（資料點不足或無意義）
    if interval_label == "日線":
        _add_indicators(hist)

    return {"symbol": symbol, "history": hist, "info": {}}


def fetch_live_price(symbol: str) -> dict:
    """輕量級即時報價，不計算指標，用於自動刷新。"""
    ticker = yf.Ticker(symbol)
    fi = ticker.fast_info
    return {
        "price":      getattr(fi, "last_price", None),
        "prev_close": getattr(fi, "previous_close", None),
        "volume":     getattr(fi, "last_volume", None),
    }


def is_trading_hours(market: str) -> bool:
    """判斷目前是否在交易時段。"""
    from zoneinfo import ZoneInfo
    from datetime import datetime, time as t

    if market == "台股":
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        if now.weekday() >= 5:
            return False
        return t(9, 0) <= now.time() <= t(13, 30)
    else:
        now = datetime.now(ZoneInfo("America/New_York"))
        if now.weekday() >= 5:
            return False
        return t(9, 30) <= now.time() <= t(16, 0)
