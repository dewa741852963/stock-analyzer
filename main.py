import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.ui.app import StockAnalyzerApp

if __name__ == "__main__":
    app = StockAnalyzerApp()
    app.mainloop()
