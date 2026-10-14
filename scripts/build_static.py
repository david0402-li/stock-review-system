# scripts/build_static.py
# -*- coding: utf-8 -*-
"""静态站点生成（支持分阶段：early / late / all）"""
import os
import re
import json
import sys
import argparse
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from data_service import (
    get_full_review, get_latest_trade_date, get_trade_dates,
    get_lhb_rich_data, fetch_concept_flow, fetch_north_flow,
    load_youzi_map, compute_market_metrics, fetch_limit_up_pool,
    fetch_limit_down_pool, fetch_broken_pool, _df_to_records,
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


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def copy_frontend():
    src_html = os.path.join(ROOT, "templates", "index.html")
    with open(src_html, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("/static/app.js", "./static/app_static.js")
    html = html.replace("/static/style.css", "./static/style.css")
    with open(os.path.join(PUBLIC, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ index.html")

    shutil.copy(os.path.join(ROOT, "static", "style.css"),
                os.path.join(STATIC_OUT, "style.css"))
    print(f"  ✅ style.css")

    with open(os.path.join(ROOT, "static", "app.js"), "r", encoding="utf-8") as f:
        app_js = f.read()

    prefix = '''
// ===== 静态模式：fetch 重写 =====
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
    }
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
'''
    with open(os.path.join(STATIC_OUT, "app_static.js"), "w", encoding="utf-8") as f:
        f.write(prefix + app_js)
    print(f"  ✅ app_static.js")


def build_early(date):
    print(f"\n[EARLY] 拉取早出数据...")
    result = {}
    metrics = compute_market_metrics(date)
    result["metrics"] = metrics
    print(f"  ✅ metrics: 涨停 {metrics['zt_count']}, 跌停 {metrics['dt_count']}")

    zt_df = fetch_limit_up_pool(date)
    dt_df = fetch_limit_down_pool(date)
    zb_df = fetch_broken_pool(date)
    result["limit_up_stocks"] = _df_to_records(zt_df, 200)
    result["limit_down_stocks"] = _df_to_records(dt_df, 100)
    result["broken_stocks"] = _df_to_records(zb_df, 100)
    print(f"  ✅ 涨停池 {len(result['limit_up_stocks'])} 条")
    return result


def build_late(date):
    print(f"\n[LATE] 拉取晚出数据...")
    result = {}
    try:
        lhb = get_lhb_rich_data(date)
        if lhb:
            result["today_stocks_lhb"] = lhb.get("today_stocks", [])
            result["three_day_stocks_lhb"] = lhb.get("three_day_stocks", [])
            result["lhb_summary"] = lhb.get("summary", {})
            # ⭐ 单独保存 lhb_${date}.json（前端 loadLhbPanel 用）
            save_json(os.path.join(DATA, f"lhb_{date}.json"),
                      {"code": 0, "data": lhb})
            print(f"  ✅ 龙虎榜: {len(result['today_stocks_lhb'])} 只, 已保存 lhb_{date}.json")
    except Exception as e:
        print(f"  ⚠️ 龙虎榜失败: {e}")

    try:
        from data_service import fetch_sector_flow
        sf = fetch_sector_flow(date, use_cache=False)
        result["sector_flow"] = sf
        print(f"  ✅ 板块资金流")
    except Exception as e:
        print(f"  ⚠️ 板块资金流失败: {e}")
    return result


def build_global():
    today = datetime.now().strftime("%Y%m%d")
    dates = get_trade_dates()
    past = [d for d in dates if d <= today]
    latest = past[-1] if past else (dates[-1] if dates else today)

    save_json(os.path.join(DATA, "trade_dates.json"), {
        "code": 0, "latest": latest, "dates": list(reversed(past[-250:])),
    })
    print(f"  ✅ trade_dates.json")

    try:
        ym = load_youzi_map()
        yz_list = [{"name": n, "keywords": k} for n, k in ym]
        save_json(os.path.join(DATA, "youzi_map.json"), {"code": 0, "data": yz_list})
        print(f"  ✅ youzi_map.json")
    except Exception as e:
        print(f"  ⚠️ 游资名单失败: {e}")

    try:
        nf = fetch_north_flow()
        save_json(os.path.join(DATA, "north_flow.json"), {"code": 0, "data": nf})
        print(f"  ✅ north_flow.json")
    except Exception as e:
        print(f"  ⚠️ 北向资金失败: {e}")


def merge_and_save(date, new_data, stage):
    file_path = os.path.join(DATA, f"review_{date}.json")
    existing = load_json(file_path) or {"code": 0, "data": {}}
    old_data = existing.get("data", {})
    old_data.update(new_data)
    old_data["_build_stage"] = stage
    old_data["_build_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(file_path, {"code": 0, "data": old_data})
    print(f"  ✅ 已合并到 review_{date}.json（stage={stage}）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["early", "late", "all"], default="all")
    args = parser.parse_args()

    import datetime as _dt

    latest_date = get_latest_trade_date()
    print(f"═══ 构建开始 ═══")
    print(f"最新交易日：{latest_date}")
    print(f"阶段：{args.stage}")

    ensure_dirs()
    print(f"\n[GLOBAL] 全局数据...")
    copy_frontend()
    build_global()

    # 取最近 5 个交易日
    all_dates = get_trade_dates()
    today = _dt.datetime.now().strftime("%Y%m%d")
    past = [d for d in all_dates if d <= today][-5:]
    print(f"\n[BUILD] 生成最近 {len(past)} 个交易日：{past}")

    for date in past:
        print(f"\n{'='*50}")
        print(f"处理 {date}")
        print(f"{'='*50}")
        try:
            if args.stage in ("early", "all"):
                data = build_early(date)
                merge_and_save(date, data, "early")
            if args.stage in ("late", "all"):
                data = build_late(date)
                merge_and_save(date, data, "late")
        except Exception as e:
            print(f"  ⚠️ {date} 失败：{e}")
            continue

    print(f"\n🎉 完成！stage={args.stage}")

    # 清理 6 天前的旧文件
    try:
        cutoff = _dt.datetime.now() - _dt.timedelta(days=6)
        cutoff_str = cutoff.strftime("%Y%m%d")
        for f in os.listdir(DATA):
            m = re.match(r"review_(\d{8})\.json", f)
            if m and m.group(1) < cutoff_str:
                os.remove(os.path.join(DATA, f))
                print(f"  🗑️ 清理旧文件：{f}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
