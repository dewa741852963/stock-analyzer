import threading
import sys
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import matplotlib
matplotlib.rcParams["axes.unicode_minus"] = False

# CJK font family list (confirmed available on this macOS system)
_CJK_FONTS = ["Heiti TC", "STHeiti", "Arial Unicode MS", "DejaVu Sans"]

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import mplfinance as mpf
import pandas as pd

from src.data.fetcher import (fetch_stock_data, find_col, fetch_live_price,
                               is_trading_hours, fetch_interval_data)
from src.data.database import list_cached
from src.config import get_api_key, get as cfg_get
from src.ui.settings_dialog import SettingsDialog

# ── Catppuccin Mocha palette ─────────────────────────────────────────────────
BG      = "#1e1e2e"
PANEL   = "#2a2a3e"
CARD    = "#181825"
SURFACE = "#313244"
ACCENT  = "#89b4fa"
GREEN   = "#a6e3a1"
RED     = "#f38ba8"
YELLOW  = "#f9e2af"
PURPLE  = "#cba6f7"
TEXT    = "#cdd6f4"
DIM     = "#6c7086"
BORDER  = "#45475a"
MONO    = "SF Mono"   # monospace font for numbers


def _apply_styles():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, font=("SF Pro Display", 12))
    s.configure("TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("TEntry", fieldbackground=CARD, foreground=TEXT,
                bordercolor=BORDER, insertcolor=TEXT, padding=4)
    s.configure("TCombobox", fieldbackground=CARD, foreground=TEXT,
                background=SURFACE, arrowcolor=TEXT, padding=4)
    s.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", TEXT)])
    s.configure("Accent.TButton", background=ACCENT, foreground=BG,
                borderwidth=0, focusthickness=0, padding=(14, 6), font=("SF Pro Display", 12, "bold"))
    s.map("Accent.TButton", background=[("active", "#74c7ec"), ("disabled", SURFACE)])
    s.configure("Ghost.TButton", background=SURFACE, foreground=TEXT,
                borderwidth=0, focusthickness=0, padding=(10, 6))
    s.map("Ghost.TButton", background=[("active", BORDER)])
    s.configure("AI.TButton", background=PURPLE, foreground=BG,
                borderwidth=0, focusthickness=0, padding=(14, 6), font=("SF Pro Display", 12, "bold"))
    s.map("AI.TButton", background=[("active", "#b4befe"), ("disabled", SURFACE)])
    s.configure("TNotebook", background=PANEL, borderwidth=0, tabmargins=0)
    s.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                padding=(16, 6), borderwidth=0, font=("SF Pro Display", 11))
    s.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXT)])
    s.configure("TScrollbar", background=SURFACE, troughcolor=CARD,
                borderwidth=0, arrowsize=12)


class StockAnalyzerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Analyzer")
        self.geometry("1440x900")
        self.minsize(1100, 700)
        self.configure(bg=BG)
        _apply_styles()

        self.stock_data = None
        self._loading = False
        self._refresh_job = None
        self._interval = "日線"
        self._build_toolbar()
        self._build_body()
        self.update_idletasks()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=PANEL, height=58)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # Bottom border line
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", side="top")

        tk.Label(bar, text="📈  Stock Analyzer", bg=PANEL, fg=TEXT,
                 font=("SF Pro Display", 16, "bold")).pack(side="left", padx=24)

        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", padx=16)

        # Symbol entry
        self.symbol_var = tk.StringVar()
        self._sym_entry = ttk.Entry(right, textvariable=self.symbol_var, width=20)
        self._sym_entry.pack(side="left", padx=6, pady=12)
        self._sym_entry.bind("<Return>", lambda _: self._start_analysis())
        self._sym_entry.insert(0, "股票代碼 (e.g. 2330)")
        self._sym_entry.bind("<FocusIn>",  lambda e: self._clear_placeholder())
        self._sym_entry.bind("<FocusOut>", lambda e: self._restore_placeholder())

        # Market / period
        self.market_var = tk.StringVar(value="台股")
        ttk.Combobox(right, textvariable=self.market_var, values=["台股", "美股"],
                     state="readonly", width=7).pack(side="left", padx=4)

        self.period_var = tk.StringVar(value="6個月")
        ttk.Combobox(right, textvariable=self.period_var,
                     values=["1個月", "3個月", "6個月", "1年", "2年"],
                     state="readonly", width=8).pack(side="left", padx=4)

        self._analyze_btn = ttk.Button(right, text="分析", style="Accent.TButton",
                                       command=self._start_analysis)
        self._analyze_btn.pack(side="left", padx=(8, 4))

        ttk.Button(right, text="⚙", style="Ghost.TButton",
                   command=self._open_settings, width=3).pack(side="left")

        # Status label (stored directly for colour updates)
        self._status_lbl = tk.Label(bar, text="", bg=PANEL, fg=DIM,
                                    font=("SF Pro Display", 11))
        self._status_lbl.pack(side="left", padx=20)

    def _clear_placeholder(self):
        if self.symbol_var.get().startswith("股票"):
            self._sym_entry.delete(0, "end")
            self._sym_entry.configure(foreground=TEXT)

    def _restore_placeholder(self):
        if not self.symbol_var.get().strip():
            self._sym_entry.insert(0, "股票代碼 (e.g. 2330)")
            self._sym_entry.configure(foreground=DIM)

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_sidebar(body)

        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self._build_tabs(main)

        # Interval switcher
        interval_bar = tk.Frame(main, bg=BG)
        interval_bar.pack(fill="x", pady=(0, 4))
        self._interval_btns = {}
        for label in ["分時", "日線", "週線", "月線"]:
            btn = tk.Button(interval_bar, text=label, bg=SURFACE, fg=DIM,
                            relief="flat", font=("SF Pro Display", 11),
                            padx=14, pady=4, cursor="hand2",
                            command=lambda l=label: self._switch_interval(l))
            btn.pack(side="left", padx=(0, 2))
            self._interval_btns[label] = btn
        self._highlight_interval("日線")

        self.chart_frame = tk.Frame(main, bg=PANEL)
        self.chart_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._show_empty_state()

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=PANEL, width=230)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # ── Stock info card ──
        self._sb_section_title(sb, "股票資訊")
        self.info_lbl = {}

        # Live indicator
        self._live_lbl = tk.Label(sb, text="", bg=PANEL, fg=DIM,
                                  font=("SF Pro Display", 10))
        self._live_lbl.pack(anchor="w", padx=14, pady=(0, 4))

        # Name (larger, prominent)
        self._name_lbl = tk.Label(sb, text="—", bg=PANEL, fg=TEXT,
                                  font=("SF Pro Display", 13, "bold"),
                                  anchor="w", wraplength=190)
        self._name_lbl.pack(fill="x", padx=14, pady=(0, 6))

        # Price (hero number)
        price_row = tk.Frame(sb, bg=PANEL)
        price_row.pack(fill="x", padx=14, pady=(0, 4))
        self._price_lbl = tk.Label(price_row, text="—", bg=PANEL, fg=TEXT,
                                   font=(MONO, 22, "bold"), anchor="w")
        self._price_lbl.pack(side="left")
        self._chg_lbl = tk.Label(price_row, text="", bg=PANEL, fg=DIM,
                                 font=(MONO, 11), anchor="w")
        self._chg_lbl.pack(side="left", padx=(8, 0))

        # Sub-info rows
        for label, key in [("代碼", "symbol"), ("成交量", "volume")]:
            self.info_lbl[key] = self._sb_row(sb, label)

        self._sb_divider(sb)

        # ── Signal badge ──
        self._sb_section_title(sb, "技術指標")

        badge_frame = tk.Frame(sb, bg=PANEL)
        badge_frame.pack(fill="x", padx=14, pady=(0, 8))
        self._signal_badge = tk.Label(badge_frame, text="  —  ", bg=SURFACE, fg=DIM,
                                      font=("SF Pro Display", 11, "bold"),
                                      padx=10, pady=4, relief="flat")
        self._signal_badge.pack(side="left")

        # Indicator rows with value labels
        self.ind_lbl = {}
        indicator_rows = [
            ("RSI", "rsi"), ("MACD", "macd"),
            ("MA20", "ma20"), ("MA50", "ma50"),
            ("布林上軌", "bbu"), ("布林下軌", "bbl"),
        ]
        for label, key in indicator_rows:
            self.ind_lbl[key] = self._sb_row(sb, label, mono=True)

        self._sb_divider(sb)

        # ── 最近查詢 ──
        self._sb_section_title(sb, "最近查詢")
        self._history_frame = tk.Frame(sb, bg=PANEL)
        self._history_frame.pack(fill="x", padx=8)
        self._refresh_history_list()

    def _sb_section_title(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=PANEL, fg=DIM,
                 font=("SF Pro Display", 9, "bold")).pack(anchor="w", padx=14, pady=(14, 4))

    def _sb_divider(self, parent):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=14, pady=8)

    def _sb_row(self, parent, label, mono=False) -> tk.Label:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=14, pady=1)
        tk.Label(row, text=label, bg=PANEL, fg=DIM,
                 font=("SF Pro Display", 11), width=7, anchor="w").pack(side="left")
        font = (MONO, 11) if mono else ("SF Pro Display", 11)
        val = tk.Label(row, text="—", bg=PANEL, fg=TEXT, font=font, anchor="w")
        val.pack(side="left")
        return val

    def _refresh_history_list(self):
        for w in self._history_frame.winfo_children():
            w.destroy()
        cached = list_cached()
        if not cached:
            tk.Label(self._history_frame, text="尚無快取資料", bg=PANEL,
                     fg=DIM, font=("SF Pro Display", 10)).pack(anchor="w", padx=6)
            return
        for item in cached[:8]:
            symbol = item["symbol"]
            card = tk.Frame(self._history_frame, bg=SURFACE, cursor="hand2")
            card.pack(fill="x", pady=2)
            tk.Label(card, text=symbol, bg=SURFACE, fg=ACCENT,
                     font=("SF Pro Display", 11, "bold"), anchor="w").pack(
                     side="left", padx=8, pady=4)
            tk.Label(card, text=item["updated_at"][5:16], bg=SURFACE, fg=DIM,
                     font=("SF Pro Display", 9), anchor="e").pack(
                     side="right", padx=6)
            for widget in (card,) + tuple(card.winfo_children()):
                widget.bind("<Button-1>", lambda e, s=symbol: self._load_from_history(s))
                widget.bind("<Enter>", lambda e, c=card: c.configure(bg=BORDER))
                widget.bind("<Leave>", lambda e, c=card: c.configure(bg=SURFACE))

    def _load_from_history(self, symbol: str):
        # 解析市場
        market = "台股" if symbol.endswith(".TW") or symbol.endswith(".TWO") else "美股"
        clean  = symbol.replace(".TW", "").replace(".TWO", "")
        self.symbol_var.set(clean)
        self._sym_entry.configure(foreground=TEXT)
        self.market_var.set(market)
        self._start_analysis()

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tabs(self, parent):
        wrap = tk.Frame(parent, bg=CARD, height=290)
        wrap.pack(fill="x", side="bottom")
        wrap.pack_propagate(False)

        nb = ttk.Notebook(wrap)
        nb.pack(fill="both", expand=True)

        # Technical chart tab
        self.ind_chart_frame = tk.Frame(nb, bg=CARD)
        nb.add(self.ind_chart_frame, text="  技術指標圖  ")

        # Fundamentals tab (2-column grid)
        fund_outer = tk.Frame(nb, bg=CARD)
        nb.add(fund_outer, text="  基本面  ")
        c = tk.Canvas(fund_outer, bg=CARD, highlightthickness=0)
        vsb = ttk.Scrollbar(fund_outer, orient="vertical", command=c.yview)
        c.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        c.pack(side="left", fill="both", expand=True)
        self.fund_inner = tk.Frame(c, bg=CARD)
        c.create_window((0, 0), window=self.fund_inner, anchor="nw")
        self.fund_inner.bind("<Configure>", lambda e: c.configure(scrollregion=c.bbox("all")))

        # AI tab
        ai_frame = tk.Frame(nb, bg=CARD)
        nb.add(ai_frame, text="  AI 分析  ")
        # 先 pack 按鈕讓它固定在底部，再讓文字區填滿剩餘空間
        self._ai_btn = ttk.Button(ai_frame, text="🤖  執行 AI 分析",
                                  style="AI.TButton", command=self._run_ai)
        self._ai_btn.pack(side="bottom", pady=6)
        self.ai_text = scrolledtext.ScrolledText(
            ai_frame, bg=CARD, fg="#ffffff", wrap="word",
            font=("SF Pro Display", 12), borderwidth=0,
            insertbackground="#ffffff", padx=12, pady=8)
        self.ai_text.pack(fill="both", expand=True)

    # ── Empty state ───────────────────────────────────────────────────────────

    def _show_empty_state(self):
        for w in self.chart_frame.winfo_children():
            w.destroy()
        container = tk.Frame(self.chart_frame, bg=PANEL)
        container.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(container, text="📊", bg=PANEL, font=("SF Pro Display", 40)).pack()
        tk.Label(container, text="輸入股票代碼開始分析", bg=PANEL, fg=TEXT,
                 font=("SF Pro Display", 14, "bold")).pack(pady=(8, 4))
        tk.Label(container, text="支援台股（2330）及美股（AAPL）", bg=PANEL, fg=DIM,
                 font=("SF Pro Display", 11)).pack()

    # ── Analysis flow ─────────────────────────────────────────────────────────

    def _start_analysis(self):
        if self._loading:
            return
        symbol = self.symbol_var.get().strip()
        if not symbol or symbol.startswith("股票"):
            self._status("請輸入股票代碼", RED)
            return
        self._set_loading(True)
        self._status("載入資料…", DIM)
        threading.Thread(
            target=self._fetch,
            args=(symbol, self.market_var.get(), self.period_var.get()),
            daemon=True
        ).start()

    def _set_loading(self, loading: bool):
        self._loading = loading
        state = "disabled" if loading else "normal"
        self._analyze_btn.configure(state=state)
        self._analyze_btn.configure(text="分析中…" if loading else "分析")

    def _fetch(self, symbol, market, period):
        try:
            data = fetch_stock_data(symbol, market, period)
            self.after(0, lambda: self._update_all(data))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _on_error(self, msg):
        self._set_loading(False)
        self._status(f"錯誤：{msg}  請確認代碼是否正確", RED)

    def _update_all(self, data):
        self.stock_data = data
        self._interval = "日線"
        self._highlight_interval("日線")
        self._update_sidebar(data)
        self._draw_kline(data)
        self._draw_indicator_chart(data)
        self._update_fundamentals(data)
        self.ai_text.delete("1.0", "end")
        self._set_loading(False)
        if data.get("from_cache"):
            cached_at = data.get("cached_at", "")[:16].replace("T", " ")
            self._status(f"💾 離線模式  快取於 {cached_at}", YELLOW)
        else:
            self._status("分析完成 ✓", GREEN)
        self._refresh_history_list()
        self._start_live_refresh()

    # ── Sidebar update ────────────────────────────────────────────────────────

    def _update_sidebar(self, data):
        hist, info, symbol = data["history"], data["info"], data["symbol"]
        last = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else last
        price = last["Close"]
        chg = price - prev["Close"]
        pct = chg / prev["Close"] * 100
        up = chg >= 0
        color = GREEN if up else RED
        arrow = "▲" if up else "▼"
        sign  = "+" if up else ""

        name = info.get("longName", info.get("shortName", symbol))
        self._name_lbl.configure(text=name[:24] if name else symbol)
        self._price_lbl.configure(text=f"{price:,.2f}", fg=color)
        self._chg_lbl.configure(text=f"{arrow} {sign}{chg:.2f} ({sign}{pct:.2f}%)", fg=color)

        self.info_lbl["symbol"].configure(text=symbol)
        self.info_lbl["volume"].configure(text=f"{int(last['Volume']):,}")

        def iv(prefix):
            col = find_col(hist, prefix)
            if col:
                v = hist[col].iloc[-1]
                return f"{v:.2f}" if pd.notna(v) else "—"
            return "—"

        rsi_str = iv("RSI_")
        if rsi_str != "—":
            rsi_val = float(rsi_str)
            if rsi_val > 70:
                rsi_color, badge_text, badge_bg = RED, "超買", "#3b1a1a"
            elif rsi_val < 30:
                rsi_color, badge_text, badge_bg = GREEN, "超賣", "#1a3b1a"
            else:
                rsi_color, badge_text, badge_bg = TEXT, "中性", SURFACE
            self.ind_lbl["rsi"].configure(text=rsi_str, fg=rsi_color)
            self._signal_badge.configure(
                text=f"  RSI {badge_text}  ", fg=rsi_color, bg=badge_bg)
        else:
            self.ind_lbl["rsi"].configure(text="—", fg=TEXT)

        self.ind_lbl["macd"].configure(text=iv("MACD_"), fg=TEXT)
        self.ind_lbl["ma20"].configure(text=iv("SMA_20"), fg=TEXT)
        self.ind_lbl["ma50"].configure(text=iv("SMA_50"), fg=TEXT)
        self.ind_lbl["bbu"].configure(text=iv("BBU_"), fg=TEXT)
        self.ind_lbl["bbl"].configure(text=iv("BBL_"), fg=TEXT)

    # ── Interval switcher ─────────────────────────────────────────────────────

    def _highlight_interval(self, label: str):
        for l, btn in self._interval_btns.items():
            if l == label:
                btn.configure(bg=ACCENT, fg=BG, font=("SF Pro Display", 11, "bold"))
            else:
                btn.configure(bg=SURFACE, fg=DIM, font=("SF Pro Display", 11))

    def _switch_interval(self, label: str):
        if not self.stock_data:
            return
        if label == self._interval:
            return
        self._interval = label
        self._highlight_interval(label)

        symbol = self.stock_data["symbol"]
        self._status(f"載入{label}…", DIM)
        threading.Thread(target=self._fetch_interval, args=(symbol, label), daemon=True).start()

    def _fetch_interval(self, symbol: str, label: str):
        try:
            period = self.period_var.get()
            data = fetch_interval_data(symbol, label, period)
            self.after(0, lambda: self._draw_chart_for_interval(data, label))
        except Exception as e:
            self.after(0, lambda: self._status(f"錯誤：{e}", RED))

    def _draw_chart_for_interval(self, data: dict, label: str):
        if label == "分時":
            self._draw_intraday(data)
        else:
            self._draw_kline(data)
        self._status("完成 ✓", GREEN)

    # ── Intraday chart (分時) ─────────────────────────────────────────────────

    def _draw_intraday(self, data: dict):
        hist = data["history"]
        symbol = data["symbol"]
        for w in self.chart_frame.winfo_children():
            w.destroy()

        if hist.empty:
            fig = Figure(figsize=(13, 5), facecolor=PANEL)
            ax = fig.add_subplot(1, 1, 1)
            ax.set_facecolor(CARD)
            ax.text(0.5, 0.5, "今日無分時資料（非交易日或盤前）",
                    ha="center", va="center", color=DIM, fontsize=12,
                    transform=ax.transAxes)
            for spine in ax.spines.values():
                spine.set_color(BORDER)
            fig.patch.set_facecolor(PANEL)
            self._embed_chart(fig, self.chart_frame)
            return

        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        prev_close = data.get("info", {}).get("previousClose") or hist["Close"].iloc[0]

        mc = mpf.make_marketcolors(
            up=GREEN, down=RED,
            edge={"up": GREEN, "down": RED},
            wick={"up": GREEN, "down": RED},
            volume={"up": GREEN, "down": RED},
        )
        style = mpf.make_mpf_style(
            base_mpf_style="nightclouds", marketcolors=mc,
            facecolor=CARD, edgecolor="#3d3d52",
            gridcolor="#2a2a3e", gridstyle=":",
            y_on_right=True,
            rc={
                "font.size": 9,
                "font.family": _CJK_FONTS,
                "axes.labelcolor": DIM,
                "xtick.color": DIM,
                "ytick.color": DIM,
                "xtick.labelsize": 8,
                "ytick.labelsize": 9,
            },
        )

        kwargs = dict(
            type="candle", volume=True, style=style, returnfig=True,
            figsize=(14, 5.8), warn_too_much_data=9999,
            volume_panel=1, panel_ratios=(4, 1),
            tight_layout=True,
            datetime_format="%H:%M",
            xrotation=0,
        )

        fig, axes = mpf.plot(df, **kwargs)
        fig.set_dpi(120)
        fig.patch.set_facecolor(CARD)

        ax_main = axes[0]

        # Previous close reference line
        ax_main.axhline(prev_close, color=DIM, linewidth=0.9,
                        linestyle="--", alpha=0.7, zorder=0)
        ax_main.annotate(
            f"前收 {prev_close:,.0f}",
            xy=(0.002, prev_close), xycoords=("axes fraction", "data"),
            color=DIM, fontsize=7.5, va="bottom", ha="left",
            fontfamily=_CJK_FONTS,
        )

        last = hist["Close"].iloc[-1]
        chg_pct = (last - prev_close) / prev_close * 100
        sign = "+" if chg_pct >= 0 else ""
        ax_main.set_title(
            f"  {symbol}  分時走勢     {last:,.2f}   {sign}{chg_pct:.2f}%",
            loc="left", color=TEXT, fontsize=10.5, fontweight="bold", pad=8,
            fontfamily=_CJK_FONTS,
        )

        for ax in axes:
            ax.set_facecolor(CARD)
            for spine in ax.spines.values():
                spine.set_color("#3d3d52")
            ax.tick_params(colors=DIM, labelsize=8.5, length=3, width=0.6)

        self._embed_chart(fig, self.chart_frame, axes=axes, df=df)

    # ── K-line chart ──────────────────────────────────────────────────────────

    def _draw_kline(self, data):
        hist = data["history"]
        info = data.get("info", {})
        for w in self.chart_frame.winfo_children():
            w.destroy()

        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

        # ── Overlay lines ─────────────────────────────────────────────────────
        add = []
        ma20 = find_col(hist, "SMA_20")
        ma50 = find_col(hist, "SMA_50")
        bbu  = find_col(hist, "BBU_")
        bbl  = find_col(hist, "BBL_")
        if ma20: add.append(mpf.make_addplot(hist[ma20].values, color="#89b4fa", width=1.8, panel=0))
        if ma50: add.append(mpf.make_addplot(hist[ma50].values, color="#f9e2af", width=1.8, panel=0))
        if bbu:  add.append(mpf.make_addplot(hist[bbu].values,  color="#585b70", width=0.9,
                                              linestyle="--", panel=0))
        if bbl:  add.append(mpf.make_addplot(hist[bbl].values,  color="#585b70", width=0.9,
                                              linestyle="--", panel=0))

        # ── Style ─────────────────────────────────────────────────────────────
        mc = mpf.make_marketcolors(
            up=GREEN, down=RED,
            edge={"up": GREEN, "down": RED},
            wick={"up": GREEN, "down": RED},
            volume={"up": GREEN, "down": RED},
        )
        style = mpf.make_mpf_style(
            base_mpf_style="nightclouds", marketcolors=mc,
            facecolor=CARD, edgecolor="#3d3d52",
            gridcolor="#2a2a3e", gridstyle=":",
            y_on_right=True,
            rc={
                "font.size": 9,
                "font.family": _CJK_FONTS,
                "axes.labelcolor": DIM,
                "xtick.color": DIM,
                "ytick.color": DIM,
                "xtick.labelsize": 9,
                "ytick.labelsize": 9,
            },
        )

        kwargs = dict(
            type="candle", volume=True, style=style, returnfig=True,
            figsize=(14, 5.8), warn_too_much_data=9999,
            volume_panel=1, panel_ratios=(4, 1),
            tight_layout=True,
        )
        if add:
            kwargs["addplot"] = add

        fig, axes = mpf.plot(df, **kwargs)
        fig.set_dpi(120)
        fig.patch.set_facecolor(CARD)

        # ── Post-process axes ─────────────────────────────────────────────────
        ax_main = axes[0]

        # Title: symbol + last price + change %
        last  = hist["Close"].iloc[-1]
        prev  = hist["Close"].iloc[-2] if len(hist) > 1 else last
        pct   = (last - prev) / prev * 100
        sign  = "+" if pct >= 0 else ""
        clr   = GREEN if pct >= 0 else RED
        name  = info.get("longName", info.get("shortName", "")) or ""
        lbl   = f"{name}  " if name else ""
        ax_main.set_title(
            f"  {lbl}{data['symbol']}     {last:,.2f}   {sign}{pct:.2f}%",
            loc="left", color=TEXT, fontsize=10.5, fontweight="bold", pad=8,
            fontfamily=_CJK_FONTS,
        )

        # Bollinger band area fill
        if bbu and bbl:
            x = range(len(df))
            ax_main.fill_between(x, hist[bbu].values, hist[bbl].values,
                                 alpha=0.06, color=ACCENT, zorder=0)

        # MA legend (top-right)
        legend_items = []
        if ma20:
            legend_items.append(ax_main.plot([], [], color="#89b4fa", lw=1.8, label="MA20")[0])
        if ma50:
            legend_items.append(ax_main.plot([], [], color="#f9e2af", lw=1.8, label="MA50")[0])
        if bbu:
            legend_items.append(ax_main.plot([], [], color="#585b70", lw=0.9, ls="--", label="BB")[0])
        if legend_items:
            ax_main.legend(handles=legend_items, loc="upper left",
                           fontsize=8.5, framealpha=0.15,
                           labelcolor=TEXT, facecolor=CARD,
                           edgecolor=BORDER, handlelength=1.5)

        # Uniform spine + tick style across all panels
        for ax in axes:
            ax.set_facecolor(CARD)
            for spine in ax.spines.values():
                spine.set_color("#3d3d52")
            ax.tick_params(colors=DIM, labelsize=8.5, length=3, width=0.6)

        self._embed_chart(fig, self.chart_frame, axes=axes, df=df)

    # ── Indicator chart ───────────────────────────────────────────────────────

    def _draw_indicator_chart(self, data):
        hist = data["history"]
        for w in self.ind_chart_frame.winfo_children():
            w.destroy()

        fig = Figure(figsize=(13, 3), facecolor=CARD)
        ax1 = fig.add_subplot(2, 1, 1)
        ax2 = fig.add_subplot(2, 1, 2)

        rsi_col = find_col(hist, "RSI_")
        if rsi_col:
            rsi = hist[rsi_col].dropna()
            x   = range(len(rsi))
            ax1.plot(x, rsi.values, color=PURPLE, linewidth=1.5)
            ax1.fill_between(x, 70, rsi.values, where=(rsi.values > 70),
                             alpha=0.15, color=RED)
            ax1.fill_between(x, 30, rsi.values, where=(rsi.values < 30),
                             alpha=0.15, color=GREEN)
            ax1.axhline(70, color=RED,   linestyle="--", alpha=0.5, linewidth=0.8)
            ax1.axhline(30, color=GREEN, linestyle="--", alpha=0.5, linewidth=0.8)
            ax1.axhline(50, color=DIM,   linestyle=":",  alpha=0.3, linewidth=0.6)
            ax1.set_ylim(0, 100)
            ax1.set_ylabel("RSI", color=DIM, fontsize=9)
            ax1.text(len(rsi) - 1, rsi.values[-1], f" {rsi.values[-1]:.1f}",
                     color=PURPLE, fontsize=8, va="center")

        macd_col = find_col(hist, "MACD_1")
        sig_col  = find_col(hist, "MACDs_")
        hist_col = find_col(hist, "MACDh_")
        if macd_col and sig_col:
            macd = hist[macd_col].dropna()
            if macd.empty:
                ax2.text(0.5, 0.5, "資料不足，MACD 需至少 26 根 K 線",
                         ha="center", va="center", color=DIM, fontsize=9,
                         transform=ax2.transAxes)
                ax2.set_ylabel("MACD", color=DIM, fontsize=9)
            else:
                sig  = hist[sig_col].reindex(macd.index)
                x    = range(len(macd))
                ax2.plot(x, macd.values, color=ACCENT, linewidth=1.2, label="MACD")
                ax2.plot(x, sig.values,  color=YELLOW,  linewidth=1.2, label="Signal")
                if hist_col:
                    hv = hist[hist_col].reindex(macd.index).values
                    ax2.bar(x, hv, color=[GREEN if v >= 0 else RED for v in hv],
                            alpha=0.5, width=0.8)
                ax2.axhline(0, color=DIM, linewidth=0.5, alpha=0.5)
                ax2.set_ylabel("MACD", color=DIM, fontsize=9)
                ax2.legend(loc="upper left", fontsize=8, framealpha=0.2,
                           labelcolor=TEXT, facecolor=CARD)

        for ax in (ax1, ax2):
            ax.set_facecolor(CARD)
            ax.tick_params(colors=DIM, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(BORDER)

        fig.tight_layout(pad=0.4)
        # pass hist for date mapping; rsi/macd are subsets so use full hist index
        self._embed_chart(fig, self.ind_chart_frame, axes=[ax1, ax2], df=hist)

    # ── Fundamentals (2-column grid) ─────────────────────────────────────────

    def _update_fundamentals(self, data):
        info = data["info"]
        for w in self.fund_inner.winfo_children():
            w.destroy()

        def fmt(key, scale=1, suffix=""):
            v = info.get(key)
            if v is None:
                return "—"
            try:
                return f"{float(v) * scale:.2f}{suffix}"
            except Exception:
                return str(v)

        items = [
            ("市值",       lambda: f"{info['marketCap']:,}" if info.get("marketCap") else "—"),
            ("本益比",     lambda: fmt("trailingPE")),
            ("EPS",        lambda: fmt("trailingEps")),
            ("殖利率",     lambda: fmt("dividendYield", 100, "%")),
            ("52W 高",     lambda: fmt("fiftyTwoWeekHigh")),
            ("52W 低",     lambda: fmt("fiftyTwoWeekLow")),
            ("Beta",       lambda: fmt("beta")),
            ("產業",       lambda: info.get("sector", "—")),
        ]

        # 2-column grid layout
        for i, (label, fn) in enumerate(items):
            try:
                value = fn()
            except Exception:
                value = "—"
            col = i % 2
            row_idx = i // 2
            cell = tk.Frame(self.fund_inner, bg=SURFACE, padx=10, pady=8)
            cell.grid(row=row_idx, column=col, padx=4, pady=4, sticky="ew")
            self.fund_inner.columnconfigure(col, weight=1)
            tk.Label(cell, text=label, bg=SURFACE, fg=DIM,
                     font=("SF Pro Display", 10)).pack(anchor="w")
            tk.Label(cell, text=value, bg=SURFACE, fg=TEXT,
                     font=(MONO, 13, "bold")).pack(anchor="w", pady=(2, 0))

    # ── AI analysis ───────────────────────────────────────────────────────────

    def _run_ai(self):
        if not self.stock_data:
            self._status("請先執行股票分析", RED)
            return
        provider = cfg_get("ai_provider")
        if provider == "gemini" and not get_api_key():
            self._show_ai("尚未設定 Gemini API Key。\n\n請點右上角 ⚙ → 選擇 AI 模型 → 填入 API Key 後儲存。")
            self._open_settings()
            return
        if provider == "ollama" and not cfg_get("ollama_url"):
            self._show_ai("尚未設定 Ollama URL。\n\n請點右上角 ⚙ → 填入 Ollama URL。")
            self._open_settings()
            return
        if provider == "custom" and not cfg_get("custom_url"):
            self._show_ai("尚未設定自訂 API URL。\n\n請點右上角 ⚙ → 填入 API Base URL。")
            self._open_settings()
            return
        self._ai_btn.configure(state="disabled", text="分析中…")
        self.ai_text.delete("1.0", "end")
        self.ai_text.insert("end", "AI 分析中，請稍候…\n")
        threading.Thread(target=self._fetch_ai, daemon=True).start()

    def _fetch_ai(self):
        try:
            from src.ai.analyzer import analyze_stock
            result = analyze_stock(self.stock_data)
        except Exception as e:
            result = f"分析失敗：{e}"
        self.after(0, lambda: self._show_ai(result))

    def _show_ai(self, text: str):
        self.ai_text.delete("1.0", "end")
        self.ai_text.insert("end", text or "（AI 未回傳任何內容）")
        self.ai_text.see("1.0")
        self._ai_btn.configure(state="normal", text="🤖  執行 AI 分析")

    # ── Chart embedding helper ────────────────────────────────────────────────

    def _embed_chart(self, fig, parent, axes=None, df=None):
        """Embed figure with zoom toolbar + TradingView-style crosshair."""
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

        # ── Toolbar ──────────────────────────────────────────────────────────
        tb_frame = tk.Frame(parent, bg=PANEL)
        tb_frame.pack(fill="x", side="bottom")
        toolbar = NavigationToolbar2Tk(canvas, tb_frame)
        toolbar.config(background=PANEL)
        for child in toolbar.winfo_children():
            try:
                child.config(background=PANEL, foreground=DIM,
                             activebackground=SURFACE, activeforeground=TEXT,
                             highlightbackground=PANEL)
            except tk.TclError:
                pass
        toolbar.update()

        all_axes = axes if axes else (fig.get_axes() or [])
        if not isinstance(all_axes, (list, tuple)):
            all_axes = [all_axes]

        # ── Scroll-wheel zoom ─────────────────────────────────────────────────
        def _on_scroll(event):
            if event.inaxes is None:
                return
            ax = event.inaxes
            factor = 0.85 if event.button == "up" else 1.18
            xlim, ylim = ax.get_xlim(), ax.get_ylim()
            cx = event.xdata if event.xdata is not None else (xlim[0]+xlim[1])/2
            cy = event.ydata if event.ydata is not None else (ylim[0]+ylim[1])/2
            ax.set_xlim([cx-(cx-xlim[0])*factor, cx+(xlim[1]-cx)*factor])
            ax.set_ylim([cy-(cy-ylim[0])*factor, cy+(ylim[1]-cy)*factor])
            canvas.draw_idle()

        canvas.mpl_connect("scroll_event", _on_scroll)

        # ── Crosshair ─────────────────────────────────────────────────────────
        v_lines = [ax.axvline(x=0, color=DIM, lw=0.8, ls="--",
                              alpha=0.85, visible=False) for ax in all_axes]
        h_lines = [ax.axhline(y=0, color=DIM, lw=0.8, ls="--",
                              alpha=0.85, visible=False) for ax in all_axes]

        # Price label on right edge of each panel
        price_ann = []
        for ax in all_axes:
            ann = ax.annotate("", xy=(1, 0.5), xycoords="axes fraction",
                              xytext=(3, 0), textcoords="offset points",
                              color=BG, fontsize=8, va="center", ha="left",
                              bbox=dict(boxstyle="round,pad=0.25",
                                        fc=TEXT, ec=TEXT, alpha=0.95),
                              clip_on=False, visible=False, zorder=15)
            price_ann.append(ann)

        # Date label below last panel
        date_ann = all_axes[-1].annotate(
            "", xy=(0.5, 0), xycoords="axes fraction",
            xytext=(0, -3), textcoords="offset points",
            color=BG, fontsize=8, va="top", ha="center",
            bbox=dict(boxstyle="round,pad=0.25", fc=TEXT, ec=TEXT, alpha=0.95),
            clip_on=False, visible=False, zorder=15)

        # OHLCV info box (top-left of first panel, only for price charts)
        has_ohlcv = df is not None and "Close" in df.columns
        info_ann = all_axes[0].annotate(
            "", xy=(0, 1), xycoords="axes fraction",
            xytext=(6, -4), textcoords="offset points",
            color=TEXT, fontsize=8.5, va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.4", fc=CARD, ec=BORDER, alpha=0.92),
            clip_on=False, visible=False, zorder=15,
            fontfamily="monospace") if has_ohlcv else None

        def _hide_all():
            for vl, hl, pa in zip(v_lines, h_lines, price_ann):
                vl.set_visible(False); hl.set_visible(False); pa.set_visible(False)
            date_ann.set_visible(False)
            if info_ann: info_ann.set_visible(False)

        def _on_move(event):
            if event.inaxes is None or event.xdata is None:
                _hide_all(); canvas.draw_idle(); return

            x, y = event.xdata, event.ydata

            for vl in v_lines:
                vl.set_xdata([x]); vl.set_visible(True)

            for ax, hl, pa in zip(all_axes, h_lines, price_ann):
                if ax == event.inaxes:
                    hl.set_ydata([y]); hl.set_visible(True)
                    ylim = ax.get_ylim()
                    yf = (y-ylim[0])/(ylim[1]-ylim[0]) if ylim[1]!=ylim[0] else .5
                    pa.xy = (1, max(.01, min(.99, yf)))
                    pa.set_text(f" {y:,.2f} ")
                    pa.set_visible(True)
                else:
                    hl.set_visible(False); pa.set_visible(False)

            if df is not None:
                xi = int(round(x))
                if 0 <= xi < len(df):
                    xlim = all_axes[-1].get_xlim()
                    xf = (x-xlim[0])/(xlim[1]-xlim[0]) if xlim[1]!=xlim[0] else .5
                    ts = df.index[xi]
                    fmt = "%Y-%m-%d %H:%M" if hasattr(ts, 'hour') and ts.hour else "%Y-%m-%d"
                    date_ann.xy = (max(.06, min(.94, xf)), 0)
                    date_ann.set_text(f" {ts.strftime(fmt)} ")
                    date_ann.set_visible(True)

                    if info_ann is not None:
                        row = df.iloc[xi]
                        o = float(row.get("Open")  or 0)
                        h2= float(row.get("High")  or 0)
                        lo= float(row.get("Low")   or 0)
                        c = float(row.get("Close") or 0)
                        v = float(row.get("Volume")or 0)
                        chg = c - o
                        info_ann.set_text(
                            f"O:{o:.2f}  H:{h2:.2f}  L:{lo:.2f}  C:{c:.2f}"
                            f"  {'▲' if chg>=0 else '▼'}{abs(chg):.2f}"
                            f"  Vol:{int(v):,}"
                        )
                        info_ann.set_visible(True)
                else:
                    date_ann.set_visible(False)
                    if info_ann: info_ann.set_visible(False)

            canvas.draw_idle()

        canvas.mpl_connect("motion_notify_event", _on_move)
        canvas.mpl_connect("figure_leave_event", lambda e: (_hide_all(), canvas.draw_idle()))
        return canvas

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _status(self, msg, color=DIM):
        self._status_lbl.configure(text=msg, fg=color)

    # ── Live price refresh ────────────────────────────────────────────────────

    def _start_live_refresh(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        self._do_live_refresh()

    def _do_live_refresh(self):
        if not self.stock_data:
            return
        market = self.market_var.get()
        symbol = self.stock_data["symbol"]
        trading = is_trading_hours(market)

        if trading:
            self._live_lbl.configure(text="🟢 即時更新中", fg=GREEN)
            threading.Thread(target=self._fetch_live, args=(symbol,), daemon=True).start()
        else:
            from datetime import datetime
            now = datetime.now().strftime("%H:%M")
            self._live_lbl.configure(text=f"⚫ 非交易時段  {now}", fg=DIM)

        # 交易時段 30 秒刷新；非交易時段 60 秒檢查一次
        interval = 30_000 if trading else 60_000
        self._refresh_job = self.after(interval, self._do_live_refresh)

    def _fetch_live(self, symbol: str):
        try:
            live = fetch_live_price(symbol)
            self.after(0, lambda: self._apply_live_price(live))
        except Exception:
            pass

    def _apply_live_price(self, live: dict):
        price = live.get("price")
        prev  = live.get("prev_close")
        vol   = live.get("volume")
        if price is None or prev is None:
            return

        chg = price - prev
        pct = chg / prev * 100
        up  = chg >= 0
        color = GREEN if up else RED
        arrow = "▲" if up else "▼"
        sign  = "+" if up else ""

        self._price_lbl.configure(text=f"{price:,.2f}", fg=color)
        self._chg_lbl.configure(
            text=f"{arrow} {sign}{chg:.2f} ({sign}{pct:.2f}%)", fg=color)
        if vol:
            self.info_lbl["volume"].configure(text=f"{int(vol):,}")

        from datetime import datetime
        self._live_lbl.configure(
            text=f"🟢 即時  更新於 {datetime.now().strftime('%H:%M:%S')}",
            fg=GREEN)

    def _on_close(self):
        if messagebox.askyesno(
            title="關閉程式",
            message="確定要關閉 Stock Analyzer 嗎？",
            icon="question",
            default="no",
        ):
            if self._refresh_job:
                self.after_cancel(self._refresh_job)
            self.destroy()
            os._exit(0)

    def _open_settings(self):
        SettingsDialog(self)
