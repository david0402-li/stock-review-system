# scripts/build_static.py
# -*- coding: utf-8 -*-
"""静态页面生成脚本：抓取数据并生成 HTML/JSON"""
import os
import json
import shutil
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_service import get_full_review, get_latest_trade_date

OUTPUT_DIR = "public"
DATA_DIR = os.path.join(OUTPUT_DIR, "data")

def build():
    date_str = get_latest_trade_date()
    print(f"[BUILD] 生成 {date_str} 的静态数据...")

    os.makedirs(DATA_DIR, exist_ok=True)
    data = get_full_review(date_str, use_cache=False)

    # 保存 JSON 数据
    json_path = os.path.join(DATA_DIR, f"{date_str}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[BUILD] ✅ 数据已保存: {json_path}")

    # 生成 index.html（简化版，实际可渲染完整页面）
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>A股复盘 - {date_str}</title></head>
<body>
<h1>A股复盘 {date_str}</h1>
<p>涨停: {data["metrics"]["zt_count"]} | 跌停: {data["metrics"]["dt_count"]}</p>
<p>上涨: {data["metrics"]["up_count"]} | 下跌: {data["metrics"]["down_count"]}</p>
<script>
fetch("./data/{date_str}.json").then(r=>r.json()).then(d=>console.log(d));
</script>
</body>
</html>'''
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[BUILD] ✅ index.html 已生成")

if __name__ == "__main__":
    build()
