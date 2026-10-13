#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史涨跌家数统计（腾讯接口版 · 快速稳定）"""
import argparse
import os
import time
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
STOCK_LIST_CSV = os.path.join(CACHE_DIR, "stock_list.csv")
BREADTH_CSV = os.path.join(CACHE_DIR, "historical_breadth.csv")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://gu.qq.com/",
}
URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def symbol_of(code):
    """000001 -> sz000001, 600000 -> sh600000, 920000 -> bj920000"""
    c = str(code).strip().zfill(6)
    if c.startswith(("4", "8", "92")):
        return "bj" + c
    if c.startswith(("0", "2", "3")):
        return "sz" + c
    return "sh" + c


def fetch_one(code, start_dt, end_dt, retry=2):
    """返回 [(date YYYYMMDD, 'up'/'down'/'flat'), ...] 或 None"""
    symbol = symbol_of(code)
    param = f"{symbol},day,{start_dt},{end_dt},300,qfq"
    for i in range(retry + 1):
        try:
            r = requests.get(URL, params={"param": param},
                             headers=HEADERS, timeout=15)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            j = r.json()
            d = j.get("data", {}).get(symbol, {})
            kline = d.get("qfqday") or d.get("day") or []
            if not kline:
                return []
            result = []
            prev_close = None
            for item in kline:
                if len(item) < 3:
                    continue
                date = item[0].replace("-", "")
                try:
                    close = float(item[2])   # 索引 2 = 收盘
                except (ValueError, TypeError):
                    continue
                if prev_close is not None and prev_close > 0:
                    if close > prev_close:
                        result.append((date, "up"))
                    elif close < prev_close:
                        result.append((date, "down"))
                    else:
                        result.append((date, "flat"))
                prev_close = close
            return result
        except Exception:
            if i < retry:
                time.sleep(0.5 * (2 ** i))
            else:
                return None
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=120,
                        help="回溯交易日天数（默认 120）")
    parser.add_argument("--workers", type=int, default=8,
                        help="并发线程数（默认 8）")
    args = parser.parse_args()

    if not os.path.exists(STOCK_LIST_CSV):
        print(f"❌ 股票列表不存在：{STOCK_LIST_CSV}")
        print("   请先运行 python3 fetch_stock_list.py")
        sys.exit(1)

    stock_list = pd.read_csv(STOCK_LIST_CSV, dtype={"code": str})
    stock_list["code"] = stock_list["code"].astype(str).str.zfill(6)
    codes = stock_list["code"].tolist()
    print(f"[1/2] 加载 {len(codes)} 只股票")

    end_dt = datetime.now().strftime("%Y-%m-%d")
    start_dt = (datetime.now() - timedelta(days=int(args.days * 1.6))).strftime("%Y-%m-%d")
    print(f"[2/2] 拉取 {start_dt} ~ {end_dt}（{args.workers} 线程）")

    daily = defaultdict(lambda: {"up": 0, "down": 0, "flat": 0})
    done = failed = 0
    t0 = time.time()

    def _task(c):
        return c, fetch_one(c, start_dt, end_dt)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(_task, c) for c in codes]
        for fut in as_completed(futures):
            code, rows = fut.result()
            done += 1
            if rows is None:
                failed += 1
            else:
                for date, direction in rows:
                    daily[date][direction] += 1
            if done % 300 == 0:
                elapsed = time.time() - t0
                speed = done / elapsed if elapsed > 0 else 0
                eta = (len(codes) - done) / speed if speed > 0 else 0
                print(f"      进度 {done}/{len(codes)}  失败 {failed}  "
                      f"用时 {elapsed:.0f}s  剩余约 {eta:.0f}s", flush=True)

    out_rows = []
    for d in sorted(daily.keys()):
        v = daily[d]
        out_rows.append({
            "date": d,
            "up_count": v["up"],
            "down_count": v["down"],
            "flat_count": v["flat"],
        })
    out = pd.DataFrame(out_rows)

    if os.path.exists(BREADTH_CSV):
        old = pd.read_csv(BREADTH_CSV, dtype={"date": str})
        merged = pd.concat([old, out]).drop_duplicates(subset=["date"], keep="last")
        merged = merged.sort_values("date").reset_index(drop=True)
        merged.to_csv(BREADTH_CSV, index=False)
        print(f"\n✅ 已合并到 {BREADTH_CSV}（累计 {len(merged)} 天）")
        print(merged.tail(10).to_string(index=False))
    else:
        out.to_csv(BREADTH_CSV, index=False)
        print(f"\n✅ 已保存到 {BREADTH_CSV}（{len(out)} 天）")
        print(out.tail(10).to_string(index=False))

    print(f"\n总用时 {time.time()-t0:.0f}s，成功 {len(codes)-failed}，失败 {failed}")


if __name__ == "__main__":
    main()
