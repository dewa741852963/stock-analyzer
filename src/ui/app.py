import threading
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import customtkinter as ctk

from src.data.fetcher import fetch_stock_data, find_col
from src.config import get_api_key
from src.ui.settings_dialog import SettingsDialog

DARK_BG = "#0f0f1a"
PANEL_BG = "#1a1a2e"
CARD_BG = "#111827"
BORDER = "#374151"
TEXT_DIM = "#9ca3af"


class StockAnalyzerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Stock Analyzer")
        self.geometry("1440x900")
        self.minsize(1100, 700)
        self.configure(fg_color=DARK_BG)

        self.stock_data = None
        self._build_toolbar()
        self._build_body()

    # ── Toolbar ──────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color=PANEL_BG, height=58, corner_radius=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="📈 Stock Analyzer", font=ctk.CTkFont(size=17, weight="bold")).pack(side="left", padx=20)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right", padx=15)

        self.symbol_entry = ctk.CTkEntry(right, placeholder_text="股票代碼 (e.g. 2330)", width=190)
        self.symbol_entry.pack(side="left", padx=5, pady=12)
        self.symbol_entry.bind("<Return>", lambda _: self._start_analysis())

        self.market_var = ctk.StringVar(value="台股")
        ctk.CTkOptionMenu(right, variable=self.market_var, values=["台股", "美股"], width=80).pack(side="left", padx=5)

        self.period_var = ctk.StringVar(value="6個月")
        ctk.CTkOptionMenu(right, variable=self.period_var, values=["1個月", "3個月", "6個月", "1年", "2年"], width=85).pack(side="left", padx=5)

        ctk.CTkButton(right, text="分析", command=self._start_analysis, width=75, fg_color="#2563eb").pack(side="left", padx=5)
        ctk.CTkButton(right, text="⚙", command=self._open_settings, width=36, fg_color=BORDER).pack(side="left", padx=(5, 0))

        self.status_lbl = ctk.CTkLabel(bar, text="", text_color=TEXT_DIM, font=ctk.CTkFont(size=12))
        self.status_lbl.pack(side="left", padx=20)

    # ── Body ─────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_sidebar(body)

        main = ctk.CTkFrame(body, fg_color="transparent")
        main.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # Bottom tabs packed first so expand goes to chart
        self._build_tabs(main)

        self.chart_frame = ctk.CTkFrame(main, fg_color=PANEL_BG, corner_radius=10)
        self.chart_frame.pack(fill="both", expand=True, pady=(0, 10))

        self._show_placeholder(self.chart_frame)

    def _build_sidebar(self, parent):
        sb = ctk.CTkFrame(parent, fg_color=PANEL_BG, width=215, corner_radius=10)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        self._sidebar_section(sb, "股票資訊")
        self.info_lbl = {}
        for label, key in [("名稱", "name"), ("代碼", "symbol"), ("現價", "price"),
                            ("漲跌", "change"), ("漲跌%", "pct"), ("成交量", "volume")]:
            self.info_lbl[key] = self._sidebar_row(sb, label)

        ctk.CTkFrame(sb, height=1, fg_color=BORDER).pack(fill="x", padx=15, pady=10)

        self._sidebar_section(sb, "技術指標")
        self.ind_lbl = {}
        for label, key in [("RSI", "rsi"), ("MACD", "macd"), ("MA20", "ma20"),
                            ("MA50", "ma50"), ("布林上軌", "bbu"), ("布林下軌", "bbl")]:
            self.ind_lbl[key] = self._sidebar_row(sb, label)

    def _sidebar_section(self, parent, title):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(12, 4), padx=15, anchor="w")

    def _sidebar_row(self, parent, label) -> ctk.CTkLabel:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(row, text=label + ":", text_color=TEXT_DIM, font=ctk.CTkFont(size=12), width=65, anchor="w").pack(side="left")
        lbl = ctk.CTkLabel(row, text="—", font=ctk.CTkFont(size=12), anchor="w")
        lbl.pack(side="left")
        return lbl

    def _build_tabs(self, parent):
        tab_wrap = ctk.CTkFrame(parent, fg_color="transparent", height=290)
        tab_wrap.pack(fill="x", side="bottom")
        tab_wrap.pack_propagate(False)

        self.tabs = ctk.CTkTabview(tab_wrap, fg_color=PANEL_BG, segmented_button_fg_color=BORDER)
        self.tabs.pack(fill="both", expand=True)

        for name in ["技術指標圖", "基本面", "AI 分析"]:
            self.tabs.add(name)

        self.ind_chart_frame = ctk.CTkFrame(self.tabs.tab("技術指標圖"), fg_color="transparent")
        self.ind_chart_frame.pack(fill="both", expand=True)

        self.fund_frame = ctk.CTkScrollableFrame(self.tabs.tab("基本面"), fg_color="transparent")
        self.fund_frame.pack(fill="both", expand=True)

        ai_tab = self.tabs.tab("AI 分析")
        self.ai_text = ctk.CTkTextbox(ai_tab, fg_color=CARD_BG, text_color="#d1d5db", font=ctk.CTkFont(size=13), wrap="word")
        self.ai_text.pack(fill="both", expand=True, pady=(5, 2))
        self.ai_btn = ctk.CTkButton(ai_tab, text="🤖 執行 AI 分析", command=self._run_ai, fg_color="#7c3aed", width=140)
        self.ai_btn.pack(pady=(0, 4))

    # ── Placeholder ───────────────────────────────────────────────────────────

    def _show_placeholder(self, frame):
        ctk.CTkLabel(frame, text="輸入股票代碼並按「分析」開始", text_color=TEXT_DIM, font=ctk.CTkFont(size=14)).place(relx=0.5, rely=0.5, anchor="center")

    # ── Analysis flow ─────────────────────────────────────────────────────────

    def _start_analysis(self):
        symbol = self.symbol_entry.get().strip()
        if not symbol:
            self._status("請輸入股票代碼", "#ef4444")
            return
        self._status("載入資料...", TEXT_DIM)
        threading.Thread(target=self._fetch, args=(symbol, self.market_var.get(), self.period_var.get()), daemon=True).start()

    def _fetch(self, symbol, market, period):
        try:
            data = fetch_stock_data(symbol, market, period)
            self.after(0, lambda: self._update_all(data))
        except Exception as e:
            self.after(0, lambda: self._status(f"錯誤：{e}", "#ef4444"))

    def _update_all(self, data):
        self.stock_data = data
        self._update_sidebar(data)
        self._draw_kline(data)
        self._draw_indicator_chart(data)
        self._update_fundamentals(data)
        self.ai_text.delete("0.0", "end")
        self._status("分析完成", "#10b981")

    # ── Sidebar update ────────────────────────────────────────────────────────

    def _update_sidebar(self, data):
        hist, info, symbol = data["history"], data["info"], data["symbol"]
        last, prev = hist.iloc[-1], hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
        price = last["Close"]
        chg = price - prev["Close"]
        pct = chg / prev["Close"] * 100
        color = "#10b981" if chg >= 0 else "#ef4444"
        sign = "+" if chg >= 0 else ""

        name = info.get("longName", info.get("shortName", symbol))
        self.info_lbl["name"].configure(text=name[:16])
        self.info_lbl["symbol"].configure(text=symbol)
        self.info_lbl["price"].configure(text=f"{price:.2f}")
        self.info_lbl["change"].configure(text=f"{sign}{chg:.2f}", text_color=color)
        self.info_lbl["pct"].configure(text=f"{sign}{pct:.2f}%", text_color=color)
        self.info_lbl["volume"].configure(text=f"{int(last['Volume']):,}")

        def iv(prefix):
            col = find_col(hist, prefix)
            if col:
                v = hist[col].iloc[-1]
                return f"{v:.2f}" if pd.notna(v) else "—"
            return "—"

        rsi_str = iv("RSI_")
        self.ind_lbl["rsi"].configure(text=rsi_str,
            text_color="#ef4444" if rsi_str != "—" and float(rsi_str) > 70
                       else "#10b981" if rsi_str != "—" and float(rsi_str) < 30 else "#d1d5db")
        self.ind_lbl["macd"].configure(text=iv("MACD_"))
        self.ind_lbl["ma20"].configure(text=iv("SMA_20"))
        self.ind_lbl["ma50"].configure(text=iv("SMA_50"))
        self.ind_lbl["bbu"].configure(text=iv("BBU_"))
        self.ind_lbl["bbl"].configure(text=iv("BBL_"))

    # ── K-line chart ──────────────────────────────────────────────────────────

    def _draw_kline(self, data):
        hist = data["history"]
        plt.close("all")
        for w in self.chart_frame.winfo_children():
            w.destroy()

        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

        add = []
        for col, color in [("SMA_20", "#60a5fa"), ("SMA_50", "#f59e0b")]:
            c = find_col(hist, col)
            if c:
                add.append(mpf.make_addplot(hist[c].values, color=color, width=1.2, panel=0))
        for col, color in [("BBU_", "#6b7280"), ("BBL_", "#6b7280")]:
            c = find_col(hist, col)
            if c:
                add.append(mpf.make_addplot(hist[c].values, color=color, width=0.8, linestyle="--", panel=0))

        mc = mpf.make_marketcolors(up="#10b981", down="#ef4444", edge="inherit", wick="inherit", volume="inherit")
        style = mpf.make_mpf_style(base_mpf_style="nightclouds", marketcolors=mc,
                                   facecolor=PANEL_BG, edgecolor=BORDER, gridcolor="#1f2937", gridstyle="--")

        kwargs = dict(type="candle", volume=True, style=style, returnfig=True,
                      figsize=(13, 5), title=f"\n{data['symbol']}", warn_too_much_data=9999)
        if add:
            kwargs["addplot"] = add

        fig, _ = mpf.plot(df, **kwargs)
        fig.patch.set_facecolor(PANEL_BG)

        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # ── Indicator chart ───────────────────────────────────────────────────────

    def _draw_indicator_chart(self, data):
        hist = data["history"]
        for w in self.ind_chart_frame.winfo_children():
            w.destroy()

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 3.2), facecolor=PANEL_BG)

        rsi_col = find_col(hist, "RSI_")
        if rsi_col:
            rsi = hist[rsi_col].dropna()
            ax1.plot(range(len(rsi)), rsi.values, color="#a78bfa", linewidth=1.5)
            ax1.axhline(70, color="#ef4444", linestyle="--", alpha=0.6, linewidth=0.8)
            ax1.axhline(30, color="#10b981", linestyle="--", alpha=0.6, linewidth=0.8)
            ax1.set_ylim(0, 100)
            ax1.set_ylabel("RSI", color=TEXT_DIM, fontsize=10)

        macd_col = find_col(hist, "MACD_1")
        sig_col = find_col(hist, "MACDs_")
        hist_col = find_col(hist, "MACDh_")
        if macd_col and sig_col:
            macd = hist[macd_col].dropna()
            sig = hist[sig_col].reindex(macd.index)
            x = range(len(macd))
            ax2.plot(x, macd.values, color="#60a5fa", linewidth=1.2, label="MACD")
            ax2.plot(x, sig.values, color="#f59e0b", linewidth=1.2, label="Signal")
            if hist_col:
                hv = hist[hist_col].reindex(macd.index).values
                ax2.bar(x, hv, color=["#10b981" if v >= 0 else "#ef4444" for v in hv], alpha=0.5, width=0.8)
            ax2.set_ylabel("MACD", color=TEXT_DIM, fontsize=10)
            ax2.legend(loc="upper left", fontsize=9, framealpha=0.3, labelcolor="#d1d5db")

        for ax in (ax1, ax2):
            ax.set_facecolor(CARD_BG)
            ax.tick_params(colors="#6b7280", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(BORDER)

        fig.tight_layout(pad=0.5)
        canvas = FigureCanvasTkAgg(fig, master=self.ind_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    # ── Fundamentals tab ──────────────────────────────────────────────────────

    def _update_fundamentals(self, data):
        info = data["info"]
        for w in self.fund_frame.winfo_children():
            w.destroy()

        def fmt_num(key, scale=1, suffix=""):
            v = info.get(key)
            if v is None:
                return "—"
            try:
                return f"{float(v) * scale:.2f}{suffix}"
            except Exception:
                return str(v)

        rows = [
            ("市值", lambda: f"{info.get('marketCap', 0):,}" if info.get("marketCap") else "—"),
            ("本益比 P/E", lambda: fmt_num("trailingPE")),
            ("EPS", lambda: fmt_num("trailingEps")),
            ("股息殖利率", lambda: fmt_num("dividendYield", 100, "%")),
            ("52週最高", lambda: fmt_num("fiftyTwoWeekHigh")),
            ("52週最低", lambda: fmt_num("fiftyTwoWeekLow")),
            ("Beta", lambda: fmt_num("beta")),
            ("產業", lambda: info.get("sector", "—")),
        ]

        for label, fn in rows:
            try:
                value = fn()
            except Exception:
                value = "—"
            row = ctk.CTkFrame(self.fund_frame, fg_color=CARD_BG, corner_radius=6)
            row.pack(fill="x", pady=2, padx=4)
            ctk.CTkLabel(row, text=label, text_color=TEXT_DIM, font=ctk.CTkFont(size=12), width=110, anchor="w").pack(side="left", padx=10, pady=6)
            ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(side="left")

    # ── AI analysis ───────────────────────────────────────────────────────────

    def _run_ai(self):
        if not self.stock_data:
            self._status("請先執行股票分析", "#ef4444")
            return
        if not get_api_key():
            self._open_settings()
            return
        self.ai_btn.configure(state="disabled", text="分析中...")
        self.ai_text.delete("0.0", "end")
        self.ai_text.insert("0.0", "AI 分析中，請稍候...\n")
        threading.Thread(target=self._fetch_ai, daemon=True).start()

    def _fetch_ai(self):
        try:
            from src.ai.analyzer import analyze_stock
            result = analyze_stock(self.stock_data)
        except Exception as e:
            result = f"分析失敗：{e}"
        self.after(0, lambda: self._show_ai(result))

    def _show_ai(self, text):
        self.ai_text.delete("0.0", "end")
        self.ai_text.insert("0.0", text)
        self.ai_btn.configure(state="normal", text="🤖 執行 AI 分析")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _status(self, msg, color=TEXT_DIM):
        self.status_lbl.configure(text=msg, text_color=color)

    def _open_settings(self):
        SettingsDialog(self)
