import os
import time
# app.py
# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request
from data_service import (
    fetch_concept_flow, fetch_sector_stocks, fetch_sector_trend, fetch_north_flow,
    get_youzi_trace,
    get_lhb_rich_data, get_lhb_stock_detail,
    get_full_review, get_recent_trade_date,
    get_trade_dates, get_latest_trade_date,
    get_stock_detail,
)

os.makedirs('cache', exist_ok=True)
app = Flask(__name__)


@app.after_request
def _no_cache(resp):
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/review")
def api_review():
    date_str = request.args.get("date") or get_latest_trade_date()
    refresh = request.args.get("refresh") == "1"
    try:
        data = get_full_review(date_str, use_cache=not refresh)
        return jsonify({"code": 0, "data": data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/trade_dates")
def api_trade_dates():
    from datetime import datetime
    dates = get_trade_dates()
    today = datetime.now().strftime("%Y%m%d")
    past = [d for d in dates if d <= today]
    latest = past[-1] if past else (dates[-1] if dates else today)
    # 返回最近 250 个交易日，降序排列
    return jsonify({
        "code": 0,
        "latest": latest,
        "dates": list(reversed(past[-250:])),
    })


@app.route("/api/stock/<code>")
def api_stock(code):
    date_str = request.args.get("date") or get_latest_trade_date()
    try:
        data = get_stock_detail(code, date_str)
        return jsonify({"code": 0, "data": data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/lhb/<date_str>")
def api_lhb(date_str):
    try:
        return jsonify({"code": 0, "data": get_lhb_rich_data(date_str)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/lhb_detail/<code>")
def api_lhb_detail(code):
    date_str = request.args.get("date") or get_latest_trade_date()
    try:
        return jsonify({"code": 0, "data": get_lhb_stock_detail(code, date_str)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/youzi_trace/<date_str>")
def api_youzi_trace(date_str):
    refresh = request.args.get("refresh") == "1"
    try:
        return jsonify({"code": 0, "data": get_youzi_trace(date_str, use_cache=not refresh)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/concept_flow/<date_str>")
def api_concept_flow(date_str):
    try:
        return jsonify({"code": 0, "data": fetch_concept_flow(date_str)})
    except Exception as e:
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/sector_stocks/<path:sector_name>")
def api_sector_stocks(sector_name):
    stype = request.args.get("type", "industry")
    try:
        return jsonify({"code": 0, "data": fetch_sector_stocks(sector_name, stype)})
    except Exception as e:
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/sector_trend/<path:sector_name>")
def api_sector_trend(sector_name):
    days = int(request.args.get("days", 30))
    try:
        return jsonify({"code": 0, "data": fetch_sector_trend(sector_name, days)})
    except Exception as e:
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/north_flow")
def api_north_flow():
    try:
        return jsonify({"code": 0, "data": fetch_north_flow()})
    except Exception as e:
        return jsonify({"code": -1, "msg": str(e)}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})




# ============ 自动刷新（每天 17:00 拉一次板块资金流） ============
import threading
from datetime import datetime as _dt2


def _auto_refresh_loop():
    """后台线程：每 30 分钟检查一次，17 点后触发当天任务"""
    done_today = {"date": None}
    while True:
        try:
            now = _dt2.now()
            today = now.strftime("%Y%m%d")
            if now.hour == 17 and now.minute < 30 and done_today["date"] != today:
                print(f"[AUTO] {today} 定时拉取板块资金流...")
                try:
                    fetch_concept_flow(today, use_cache=False)
                    from data_service import fetch_sector_flow as _fsf
                    _fsf(today, use_cache=False)
                    done_today["date"] = today
                    print(f"[AUTO] {today} 完成")
                except Exception as e:
                    print(f"[AUTO] 失败: {e}")
        except Exception as e:
            print(f"[AUTO] 循环异常: {e}")
        time.sleep(1800)   # 30 分钟


threading.Thread(target=_auto_refresh_loop, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
