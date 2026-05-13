import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import customtkinter as ctk
from src.ui.app import StockAnalyzerApp

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = StockAnalyzerApp()
    app.mainloop()
