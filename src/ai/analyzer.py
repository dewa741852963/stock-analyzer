import pandas as pd
from src.config import get, load_config
from src.data.fetcher import find_col


def analyze_stock(data: dict) -> str:
    provider = get("ai_provider")
    if provider == "gemini":
        return _analyze_gemini(data)
    elif provider == "ollama":
        return _analyze_ollama(data)
    elif provider == "custom":
        return _analyze_custom(data)
    return "請在設定中選擇 AI 模型。"


def _build_prompt(data: dict) -> str:
    hist, info, symbol = data["history"], data["info"], data["symbol"]
    last = hist.iloc[-1]
    prev = hist.iloc[-2] if len(hist) > 1 else last
    price = last["Close"]
    pct   = (price - prev["Close"]) / prev["Close"] * 100
    sign  = "+" if pct >= 0 else ""

    def val(prefix):
        col = find_col(hist, prefix)
        if col:
            v = hist[col].iloc[-1]
            return f"{v:.2f}" if pd.notna(v) else "N/A"
        return "N/A"

    return f"""你是一位專業的股票技術分析師，請用繁體中文分析以下數據：

股票代碼：{symbol}
公司名稱：{info.get('longName', info.get('shortName', symbol))}
當前價格：{price:.2f}
今日漲跌：{sign}{pct:.2f}%

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


def _analyze_gemini(data: dict) -> str:
    api_key = get("gemini_api_key")
    if not api_key:
        return "請在設定中填入 Gemini API Key。"
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
    response = model.generate_content(_build_prompt(data))
    return response.text


def _analyze_ollama(data: dict) -> str:
    import urllib.request, json
    url   = get("ollama_url").rstrip("/")
    model = get("ollama_model") or "llama3"
    if not url:
        return "請在設定中填入 Ollama URL。"

    payload = json.dumps({
        "model": model,
        "prompt": _build_prompt(data),
        "stream": False,
    }).encode()

    try:
        req = urllib.request.Request(
            f"{url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("response", "Ollama 未回傳結果")
    except Exception as e:
        return f"Ollama 連線失敗：{e}\n\n請確認 Ollama 已啟動並執行指定模型。"


def _analyze_custom(data: dict) -> str:
    import urllib.request, json
    url   = get("custom_url").rstrip("/")
    model = get("custom_model")
    key   = get("custom_api_key") or "no-key"
    if not url:
        return "請在設定中填入 API URL。"

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": _build_prompt(data)}],
        "temperature": 0.7,
    }).encode()

    try:
        req = urllib.request.Request(
            f"{url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"自訂 API 連線失敗：{e}\n\n請確認 URL 和模型名稱是否正確。"
