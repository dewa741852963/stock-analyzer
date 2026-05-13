import tkinter as tk
from tkinter import ttk
from src.config import get_api_key, set_api_key

BG    = "#1e1e2e"
CARD  = "#12121f"
TEXT  = "#cdd6f4"
DIM   = "#6c7086"
BORDER= "#45475a"


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("設定")
        self.geometry("480x210")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.grab_set()
        self.transient(parent)

        tk.Label(self, text="Gemini API Key 設定", bg=BG, fg=TEXT,
                 font=("SF Pro Display", 14, "bold")).pack(pady=(20, 4))
        tk.Label(self, text="前往 aistudio.google.com 取得免費 API Key",
                 bg=BG, fg=DIM, font=("SF Pro Display", 11)).pack()

        self.key_var = tk.StringVar()
        entry = tk.Entry(self, textvariable=self.key_var, show="*", width=46,
                         bg=CARD, fg=TEXT, insertbackground=TEXT,
                         relief="flat", font=("SF Pro Display", 12))
        entry.pack(pady=16, ipady=6, padx=30)
        existing = get_api_key()
        if existing:
            self.key_var.set(existing)

        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack()

        tk.Button(btn_frame, text="儲存", command=self._save,
                  bg="#2563eb", fg="white", relief="flat",
                  font=("SF Pro Display", 12), padx=20, pady=6,
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(btn_frame, text="取消", command=self.destroy,
                  bg=BORDER, fg=TEXT, relief="flat",
                  font=("SF Pro Display", 12), padx=20, pady=6,
                  cursor="hand2").pack(side="left", padx=6)

    def _save(self):
        key = self.key_var.get().strip()
        if key:
            set_api_key(key)
        self.destroy()
