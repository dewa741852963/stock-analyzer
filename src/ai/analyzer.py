import pandas as pd
from src.config import get_api_key
from src.data.fetcher import find_col


def analyze_stock(data: dict) -> str:
    api_key = get_api_key()
    if not api_key:
        return "請先在設定中填入 Gemini API Key。"

    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash-latest")

    hist = data["history"]
    info = data["info"]
    symbol = data["symbol"]

    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else last
    current_price = last["Close"]
    change_pct = (current_price - prev["Close"]) / prev["Close"] * 100

    def val(prefix):
        col = find_col(hist, prefix)
        if col:
            v = hist[col].iloc[-1]
            return f"{v:.2f}" if pd.notna(v) else "N/A"
        return "N/A"

    prompt = f"""你是一位專業的股票技術分析師，請用繁體中文分析以下數據：

股票代碼：{symbol}
公司名稱：{info.get('longName', info.get('shortName', symbol))}
當前價格：{current_price:.2f}
今日漲跌：{'+' if change_pct >= 0 else ''}{change_pct:.2f}%

【技術指標】
RSI（14）：{val('RSI_')}
MACD：{val('MACD_')}
MA20：{val('SMA_20')}
MA50：{val('SMA_50')}
布林上軌：{val('BBU_')}
布林下軌：{val('BBL_')}
近30日最高：{hist['High'].tail(30).max():.2f}
近30日最低：{hist['Low'].tail(30).min():.2f}

【基本面】
P/E：{info.get('trailingPE', 'N/A')}
EPS：{info.get('trailingEps', 'N/A')}
市值：{info.get('marketCap', 'N/A')}

請提供：
1. **技術面分析**（RSI、MACD、均線）
2. **趨勢判斷**（多頭/空頭/盤整）
3. **支撐與壓力位**
4. **操作建議**（買進/持有/觀望/減碼）
5. **風險提示**

每點2-3句，簡潔有力。"""

    response = model.generate_content(prompt)
    return response.text
