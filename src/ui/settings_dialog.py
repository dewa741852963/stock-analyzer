import tkinter as tk
from tkinter import ttk
from src.config import load_config, set_values

BG     = "#1e1e2e"
CARD   = "#181825"
SURFACE= "#313244"
TEXT   = "#cdd6f4"
DIM    = "#6c7086"
BORDER = "#45475a"
ACCENT = "#89b4fa"
GREEN  = "#a6e3a1"


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("設定")
        self.geometry("520x400")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()
        self.transient(parent)

        cfg = load_config()

        # Title
        tk.Label(self, text="⚙  設定", bg=BG, fg=TEXT,
                 font=("SF Pro Display", 15, "bold")).pack(pady=(20, 4), anchor="w", padx=24)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(0, 16))

        # ── AI 模型選擇 ──
        tk.Label(self, text="AI 分析模型", bg=BG, fg=DIM,
                 font=("SF Pro Display", 10, "bold")).pack(anchor="w", padx=24)

        self.provider_var = tk.StringVar(value=cfg.get("ai_provider", "gemini"))

        providers = [
            ("gemini",  "☁  Gemini API（雲端，需要 API Key）"),
            ("ollama",  "🖥  Ollama（本地，免費）"),
            ("custom",  "🔧  自訂（LM Studio / 其他 OpenAI 相容）"),
        ]
        for value, label in providers:
            tk.Radiobutton(self, text=label, variable=self.provider_var, value=value,
                           bg=BG, fg=TEXT, selectcolor=SURFACE, activebackground=BG,
                           activeforeground=TEXT, font=("SF Pro Display", 12),
                           command=self._on_provider_change).pack(anchor="w", padx=32, pady=2)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=24, pady=12)

        # ── Dynamic settings area ──
        self._settings_frame = tk.Frame(self, bg=BG)
        self._settings_frame.pack(fill="x", padx=24)

        # Store all entry vars
        self.gemini_key_var  = tk.StringVar(value=cfg.get("gemini_api_key", ""))
        self.ollama_url_var  = tk.StringVar(value=cfg.get("ollama_url", "http://127.0.0.1:11434"))
        self.ollama_model_var= tk.StringVar(value=cfg.get("ollama_model", "llama3"))
        self.custom_url_var  = tk.StringVar(value=cfg.get("custom_url", ""))
        self.custom_model_var= tk.StringVar(value=cfg.get("custom_model", ""))
        self.custom_key_var  = tk.StringVar(value=cfg.get("custom_api_key", ""))

        self._render_provider_settings()

        # Buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(side="bottom", pady=16)
        tk.Button(btn_frame, text="儲存", command=self._save,
                  bg=ACCENT, fg=BG, relief="flat",
                  font=("SF Pro Display", 12, "bold"), padx=24, pady=7,
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(btn_frame, text="取消", command=self.destroy,
                  bg=SURFACE, fg=TEXT, relief="flat",
                  font=("SF Pro Display", 12), padx=24, pady=7,
                  cursor="hand2").pack(side="left", padx=6)

    def _on_provider_change(self):
        for w in self._settings_frame.winfo_children():
            w.destroy()
        self._render_provider_settings()

    def _render_provider_settings(self):
        p = self.provider_var.get()
        if p == "gemini":
            self._field("Gemini API Key", self.gemini_key_var, show="*",
                        hint="前往 aistudio.google.com 取得免費 API Key")
        elif p == "ollama":
            self._field("Ollama URL", self.ollama_url_var,
                        hint="預設 http://127.0.0.1:11434")
            self._field("模型名稱", self.ollama_model_var,
                        hint="例如：llama3、mistral、gemma2")
            self._ollama_hint()
        elif p == "custom":
            self._field("API Base URL", self.custom_url_var,
                        hint="例如：http://localhost:1234/v1")
            self._field("模型名稱", self.custom_model_var,
                        hint="例如：lmstudio-community/Meta-Llama-3-8B-Instruct")
            self._field("API Key（可留空）", self.custom_key_var, show="*")

    def _field(self, label, var, show=None, hint=""):
        tk.Label(self._settings_frame, text=label, bg=BG, fg=DIM,
                 font=("SF Pro Display", 11)).pack(anchor="w", pady=(6, 2))
        kwargs = dict(textvariable=var, width=52, bg=CARD, fg=TEXT,
                      insertbackground=TEXT, relief="flat",
                      font=("SF Pro Display", 12))
        if show:
            kwargs["show"] = show
        tk.Entry(self._settings_frame, **kwargs).pack(anchor="w", ipady=5)
        if hint:
            tk.Label(self._settings_frame, text=hint, bg=BG, fg=DIM,
                     font=("SF Pro Display", 9)).pack(anchor="w")

    def _ollama_hint(self):
        hint = tk.Frame(self._settings_frame, bg=SURFACE, padx=10, pady=8)
        hint.pack(fill="x", pady=(10, 0))
        tk.Label(hint, text="💡 尚未安裝 Ollama？", bg=SURFACE, fg=TEXT,
                 font=("SF Pro Display", 11, "bold")).pack(anchor="w")
        tk.Label(hint, text="前往 ollama.com 下載，安裝後執行：ollama pull llama3",
                 bg=SURFACE, fg=DIM, font=("SF Pro Display", 10)).pack(anchor="w")

    def _save(self):
        p = self.provider_var.get()
        set_values(
            ai_provider=p,
            gemini_api_key=self.gemini_key_var.get().strip(),
            ollama_url=self.ollama_url_var.get().strip(),
            ollama_model=self.ollama_model_var.get().strip(),
            custom_url=self.custom_url_var.get().strip(),
            custom_model=self.custom_model_var.get().strip(),
            custom_api_key=self.custom_key_var.get().strip(),
        )
        self.destroy()
