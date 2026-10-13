#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立拉取全市场股票列表（新浪接口 · 每页100条 · 断点保存）"""
import time
import os
import sys
import requests
import pandas as pd

OUT_CSV = "cache/stock_list.csv"
os.makedirs("cache", exist_ok=True)

URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
       "Market_Center.getHQNodeData")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://finance.sina.com.cn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def fetch_page(page, node="hs_a", retry=3):
    for i in range(retry + 1):
        try:
            r = requests.get(URL, params={
                "page": page, "num": 100, "sort": "symbol",
                "asc": 1, "node": node,
            }, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            text = r.text.strip()
            if not text or text == "null":
                return []
            return r.json() or []
        except Exception as e:
            if i < retry:
                wait = 1.5 * (2 ** i)
                print(f"    page {page} 失败（第 {i+1} 次）: {str(e)[:80]}，{wait:.1f}s 后重试", flush=True)
                time.sleep(wait)
            else:
                print(f"    page {page} 最终失败: {str(e)[:80]}", flush=True)
                return None
    return None


def fetch_by_node(node, max_pages=90, label=""):
    """按 node 逐页拉，返回 rows"""
    print(f"\n--- 拉取 [{node}] {label} ---")
    rows = []
    seen = set()
    fail = 0
    for page in range(1, max_pages + 1):
        data = fetch_page(page, node=node)
        if data is None:
            fail += 1
            if fail >= 3:
                print(f"    连续 3 页失败，停止")
                break
            continue
        if not data:
            print(f"    page {page} 空，结束")
            break
        fail = 0
        new = 0
        for item in data:
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            rows.append({"code": code, "name": name})
            new += 1
        if page % 10 == 0 or len(data) < 100:
            print(f"    page {page}: 本页 {len(data)}，新增 {new}，累计 {len(rows)}", flush=True)
        if len(data) < 100:
            break
        time.sleep(0.25)
    print(f"  [{node}] 完成，共 {len(rows)} 只")
    return rows


def main():
    print("=== 拉取全市场股票列表（新浪 · 多 node）===")
    t0 = time.time()
    all_rows = []

    # 沪深A股（hs_a 已覆盖主板/创业板/科创板/北交所）
    all_rows += fetch_by_node("hs_a", max_pages=90, label="沪深京 A 股")

    if not all_rows:
        print("❌ hs_a 没拉到任何数据")
        sys.exit(1)

    df = pd.DataFrame(all_rows)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df = df.drop_duplicates(subset=["code"]).reset_index(drop=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\n✅ 共 {len(df)} 只，已保存到 {OUT_CSV}，用时 {time.time()-t0:.1f}s")

    # 按前缀统计
    print("\n--- 代码段分布 ---")
    for prefix, label in [
        ("000", "深主板"), ("001", "深主板"), ("002", "中小板"), ("003", "深主板"),
        ("300", "创业板"), ("301", "创业板"),
        ("600", "沪主板"), ("601", "沪主板"), ("603", "沪主板"), ("605", "沪主板"),
        ("688", "科创板"), ("689", "科创板"),
        ("920", "北交所"), ("8", "北交所"), ("4", "北交所"),
    ]:
        n = sum(1 for c in df["code"] if c.startswith(prefix))
        if n:
            print(f"  {prefix}xxx {label}: {n}")
    print(df.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
