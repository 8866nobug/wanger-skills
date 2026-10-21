import os
import sys

# 允许 tests 以包形式导入 excalidraw（把 scripts/ 加入 sys.path）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
