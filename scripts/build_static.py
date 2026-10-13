# scripts/build_static.py
# -*- coding: utf-8 -*-
"""静态站点生成：抓数据 → 生成 public/ 目录"""
import os
import json
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data_service import (
    get_full_review, get_latest_trade_date, get_trade_dates,
    get_lhb_rich_data, fetch_concept_flow, fetch_north_flow,
    load_youzi_map,
)

PUBLIC = os.path.join(ROOT, "public")
DATA = os.path.join(PUBLIC, "data")
STATIC_OUT = os.path.join(PUBLIC, "static")


def ensure_dirs():
    for d in [PUBLIC, DATA, STATIC_OUT]:
        os.makedirs(d, exist_ok=True)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def copy_frontend():
    """复制 HTML/CSS/JS 到 public/，并给 app.js 注入 fetch 重写逻辑"""
    # index.html
    src_html = os.path.join(ROOT, "templates", "index.html")
    dst_html = os.path.join(PUBLIC, "index.html")
    with open(src_html, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/static/app.js", "./static/app_static.js")
    html = html.replace("/static/style.css", "./static/style.css")
    with open(dst_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ index.html")

    # style.css
    shutil.copy(os.path.join(ROOT, "static", "style.css"),
                os.path.join(STATIC_OUT, "style.css"))
    print(f"  ✅ style.css")

    # app.js + fetch 重写
    with open(os.path.join(ROOT, "static", "app.js"), "r", encoding="utf-8") as f:
        app_js = f.read()

    prefix = '''
// ===== 静态模式：fetch 重写（部署到 Cloudflare Pages 时用） =====
const ORIG_FETCH = window.fetch.bind(window);
window.fetch = async function(url, ...args) {
    if (typeof url !== "string") return ORIG_FETCH(url, ...args);
    let m;
    if (m = url.match(/^\\/api\\/review\\?date=(\\d+)/)) {
        url = `./data/review_${m[1]}.json`;
    } else if (url.startsWith("/api/trade_dates")) {
        url = "./data/trade_dates.json";
    } else if (m = url.match(/^\\/api\\/lhb\\/(\\d+)/)) {
        url = `./data/lhb_${m[1]}.json`;
    } else if (m = url.match(/^\\/api\\/concept_flow\\/(\\d+)/)) {
        url = `./data/concept_flow_${m[1]}.json`;
    } else if (url.startsWith("/api/north_flow")) {
        url = "./data/north_flow.json";
    } else if (m = url.match(/^\\/api\\/youzi_trace\\/(\\d+)/)) {
        url = `./data/youzi_trace_${m[1]}.json`;
    } else if (m = url.match(/^\\/api\\/sector_stocks\\/([^?]+)/)) {
        url = `./data/sector_stocks_${decodeURIComponent(m[1])}.json`;
    } else if (m = url.match(/^\\/api\\/sector_trend\\/([^?]+)/)) {
        url = `./data/sector_trend_${decodeURIComponent(m[1])}.json`;
    } else if (m = url.match(/^\\/api\\/lhb_detail\\/(\\d+)/)) {
        url = `./data/lhb_detail_${m[1]}.json`;
    }
    // 静态文件 404 时返回空结构，避免崩溃
    try {
        const res = await ORIG_FETCH(url, ...args);
        if (!res.ok) {
            return new Response(JSON.stringify({code: 0, data: {}}),
                {status: 200, headers: {"Content-Type": "application/json"}});
        }
        return res;
    } catch (e) {
        return new Response(JSON.stringify({code: 0, data: {}}),
            {status: 200, headers: {"Content-Type": "application/json"}});
    }
};
// ===== 静态模式 end =====

'''
    with open(os.path.join(STATIC_OUT, "app_static.js"), "w", encoding="utf-8") as f:
        f.write(prefix + app_js)
    print(f"  ✅ app_static.js (含 fetch 重写)")


def build_data():
    """生成所有静态 JSON 数据"""
    date = get_latest_trade_date()
    print(f"\n[BUILD] 生成 {date} 的静态数据...")

    # 1. 交易日列表
    dates = get_trade_dates()
    today = datetime.now().strftime("%Y%m%d")
    past = [d for d in dates if d <= today]
    latest = past[-1] if past else (dates[-1] if dates else today)
    save_json(os.path.join(DATA, "trade_dates.json"), {
        "code": 0,
        "latest": latest,
        "dates": list(reversed(past[-250:])),
    })
    print(f"  ✅ trade_dates.json")

    # 2. 完整复盘数据
    review = get_full_review(date, use_cache=False)
    save_json(os.path.join(DATA, f"review_{date}.json"), {"code": 0, "data": review})
    print(f"  ✅ review_{date}.json")

    # 3. 龙虎榜
    try:
        lhb = get_lhb_rich_data(date)
        save_json(os.path.join(DATA, f"lhb_{date}.json"), {"code": 0, "data": lhb})
        print(f"  ✅ lhb_{date}.json")
    except Exception as e:
        print(f"  ⚠️ 龙虎榜失败: {e}")

    # 4. 概念资金流
    try:
        cf = fetch_concept_flow(date, use_cache=False)
        save_json(os.path.join(DATA, f"concept_flow_{date}.json"), {"code": 0, "data": cf})
        print(f"  ✅ concept_flow_{date}.json")
    except Exception as e:
        print(f"  ⚠️ 概念资金流失败: {e}")

    # 5. 北向资金
    try:
        nf = fetch_north_flow()
        save_json(os.path.join(DATA, "north_flow.json"), {"code": 0, "data": nf})
        print(f"  ✅ north_flow.json")
    except Exception as e:
        print(f"  ⚠️ 北向资金失败: {e}")

    # 6. 游资名单
    try:
        ym = load_youzi_map()
        # 转换成前端期望的格式（用 youzi_map.json 作为对照）
        yz_list = [{"name": n, "keywords": k} for n, k in ym]
        save_json(os.path.join(DATA, "youzi_map.json"), {"code": 0, "data": yz_list})
        print(f"  ✅ youzi_map.json")
    except Exception as e:
        print(f"  ⚠️ 游资名单失败: {e}")

    return date


def main():
    print("[1/3] 创建目录...")
    ensure_dirs()
    print(f"[2/3] 复制前端资源...")
    copy_frontend()
    print(f"[3/3] 生成数据...")
    date = build_data()
    print(f"\n🎉 完成！public/ 已生成（{date}）")
    print(f"   📁 {PUBLIC}")


if __name__ == "__main__":
    main()
