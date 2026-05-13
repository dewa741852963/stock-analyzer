import customtkinter as ctk
from src.config import get_api_key, set_api_key


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("設定")
        self.geometry("460x200")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="Gemini API Key 設定", font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="前往 aistudio.google.com 取得免費 API Key", text_color="#9ca3af", font=ctk.CTkFont(size=12)).pack()

        self.key_entry = ctk.CTkEntry(self, placeholder_text="貼上你的 Gemini API Key", width=380, show="*")
        self.key_entry.pack(pady=15)
        existing = get_api_key()
        if existing:
            self.key_entry.insert(0, existing)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack()
        ctk.CTkButton(btn_frame, text="儲存", command=self._save, width=100, fg_color="#2563eb").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="取消", command=self.destroy, width=100, fg_color="#374151").pack(side="left", padx=5)

    def _save(self):
        key = self.key_entry.get().strip()
        if key:
            set_api_key(key)
        self.destroy()
