# data_service.py
# -*- coding: utf-8 -*-
"""复盘系统数据服务模块"""
import akshare as ak
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import os
try:
    from kaipanla_crawler import KaipanlaCrawler
except ImportError:
    KaipanlaCrawler = None

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def get_recent_trade_date():
    today = datetime.now()
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    return today.strftime("%Y%m%d")


def prev_trade_date(date_str):
    d = datetime.strptime(date_str, "%Y%m%d") - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def _retry_call(fn, *args, retry=3, delay=1.5, **kwargs):
    """通用重试"""
    for i in range(retry + 1):
        try:
            r = fn(*args, **kwargs)
            if r is not None:
                return r
        except Exception:
            if i < retry:
                time.sleep(delay * (i + 1))
    return None


def safe_call(func, *args, **kwargs):
    try:
        df = func(*args, **kwargs)
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception as e:
        print(f"[WARN] {getattr(func, '__name__', func)} 调用失败: {e}")
        return pd.DataFrame()


def fetch_limit_up_pool(date_str):
    df = safe_call(ak.stock_zt_pool_em, date=date_str)
    if df.empty:
        return df
    rename_map = {
        "代码": "code", "名称": "name", "涨跌幅": "pct_chg",
        "最新价": "price", "成交额": "amount", "流通市值": "float_mv",
        "总市值": "total_mv", "换手率": "turnover", "封板资金": "seal_amount",
        "首次封板时间": "first_seal_time", "最后封板时间": "last_seal_time",
        "炸板次数": "break_count", "涨停统计": "limit_stat",
        "连板数": "consecutive_days", "所属行业": "industry",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    return df


def fetch_limit_down_pool(date_str):
    df = safe_call(ak.stock_zt_pool_dtgc_em, date=date_str)
    if df.empty:
        return df
    rename_map = {
        "代码": "code", "名称": "name", "涨跌幅": "pct_chg",
        "最新价": "price", "成交额": "amount", "流通市值": "float_mv",
        "换手率": "turnover", "封单资金": "seal_amount",
        "连续跌停": "consecutive_days", "所属行业": "industry",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    return df


def fetch_broken_pool(date_str):
    df = safe_call(ak.stock_zt_pool_zbgc_em, date=date_str)
    if df.empty:
        return df
    rename_map = {
        "代码": "code", "名称": "name", "涨跌幅": "pct_chg",
        "最新价": "price", "涨停价": "limit_price", "成交额": "amount",
        "流通市值": "float_mv", "总市值": "total_mv", "换手率": "turnover",
        "涨速": "speed", "首次封板时间": "first_seal_time",
        "炸板次数": "break_count", "振幅": "amplitude",
        "所属行业": "industry",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    return df


def fetch_dragon_tiger(date_str):
    df = safe_call(ak.stock_lhb_detail_em, start_date=date_str, end_date=date_str)
    if df.empty:
        return df
    rename_map = {
        "序号": "seq", "代码": "code", "名称": "name", "上榜日": "date",
        "解读": "interpretation", "收盘价": "close", "涨跌幅": "pct_chg",
        "龙虎榜净买额": "net_buy", "龙虎榜买入额": "buy_amount",
        "龙虎榜卖出额": "sell_amount", "龙虎榜成交额": "total_amount",
        "市场总成交额": "market_amount", "净买额占总成交比": "net_buy_ratio",
        "成交额占总成交比": "amount_ratio", "换手率": "turnover",
        "流通市值": "float_mv", "上榜原因": "reason",
        "上榜后1日": "after_1d", "上榜后2日": "after_2d",
        "上榜后5日": "after_5d", "上榜后10日": "after_10d",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    return df


def fetch_all_stock_spot():
    return safe_call(ak.stock_zh_a_spot_em)


def compute_market_metrics(date_str):
    """计算市场核心指标（涨跌家数优先开盘啦）"""
    zt_df = fetch_limit_up_pool(date_str)
    dt_df = fetch_limit_down_pool(date_str)
    zb_df = fetch_broken_pool(date_str)

    zt_count = len(zt_df)
    dt_count = len(dt_df)
    zb_count = len(zb_df)
    denom = zt_count + zb_count
    break_rate = round(zb_count / denom * 100, 2) if denom > 0 else 0.0

    # 连板梯队
    lianban_tiers = {}
    if not zt_df.empty and "consecutive_days" in zt_df.columns:
        tmp = zt_df.copy()
        tmp["consecutive_days"] = pd.to_numeric(
            tmp["consecutive_days"], errors="coerce"
        ).fillna(1).astype(int)
        for days in sorted(tmp["consecutive_days"].unique(), reverse=True):
            tier = tmp[tmp["consecutive_days"] == days]
            cols = [c for c in ["code", "name", "industry", "pct_chg"] if c in tier.columns]
            lianban_tiers[int(days)] = tier[cols].to_dict("records")

    # 题材分布
    theme_dist = {}
    if not zt_df.empty and "industry" in zt_df.columns:
        vc = zt_df["industry"].fillna("未知").value_counts().head(15)
        theme_dist = {str(k): int(v) for k, v in vc.items()}

    # ---------- 涨跌家数（开盘啦优先） ----------
    up_count = down_count = flat_count = 0
    promote_rate = 0.0
    yesterday_avg_pct = 0.0
    up_source = "none"

    # 方案1：开盘啦爬虫
    try:
        kpl_data = kpl_fetch_daily_data(date_str)
        if kpl_data is not None and not kpl_data.empty:
            try:
                keys = list(kpl_data.index) + list(kpl_data.columns)
                print(f"[KPL] 返回可用字段（前30个）: {keys[:30]}")
            except Exception:
                pass

            def _pick(df, *candidates):
                for c in candidates:
                    # 先看 index
                    try:
                        if c in df.index:
                            v = df.loc[c]
                            if hasattr(v, "iloc"):
                                v = v.iloc[0]
                            return float(v)
                    except Exception:
                        pass
                    # 再看 columns
                    try:
                        if c in df.columns:
                            v = df[c].iloc[0] if hasattr(df[c], "iloc") else df[c]
                            return float(v)
                    except Exception:
                        pass
                return 0.0

            up_count   = int(_pick(kpl_data, "上涨家数", "上涨", "upCount", "up_count"))
            down_count = int(_pick(kpl_data, "下跌家数", "下跌", "downCount", "down_count"))
            flat_count = int(_pick(kpl_data, "平盘家数", "平盘", "flatCount"))
            promote_rate = _pick(kpl_data, "晋级率", "promoteRate", "promote_rate")
            yesterday_avg_pct = _pick(kpl_data, "昨日涨停表现", "昨日涨停均涨幅", "yesterdayPct")

            if up_count > 0 or down_count > 0:
                up_source = "kpl_crawler"
                print(f"[KPL] 涨跌家数来自开盘啦: 涨 {up_count}, 跌 {down_count}, 平盘 {flat_count}")
    except Exception as e:
        print(f"[WARN] 开盘啦涨跌家数失败: {e}")

    # 方案2：东财 push2 兜底
    if up_source == "none":
        try:
            up_count, down_count, flat_count = _fetch_updown_push2()
            if up_count > 0 or down_count > 0:
                up_source = "push2"
                print(f"[DATA] 涨跌家数来自 push2: 涨 {up_count} 跌 {down_count}")
        except Exception as e:
            print(f"[WARN] push2 涨跌家数失败: {e}")

    # 方案3：乐咕乐股兜底
    if up_source == "none":
        try:
            act_df = ak.stock_market_activity_legu()
            if act_df is not None and not act_df.empty:
                item_col  = "item"  if "item"  in act_df.columns else act_df.columns[0]
                value_col = "value" if "value" in act_df.columns else act_df.columns[1]
                for _, row in act_df.iterrows():
                    item = str(row[item_col]).strip()
                    try:
                        value = int(float(row[value_col]))
                    except Exception:
                        continue
                    if item == "上涨":   up_count = value
                    elif item == "下跌": down_count = value
                    elif item == "平盘": flat_count = value
                if up_count > 0 or down_count > 0:
                    up_source = "legu"
                    print(f"[DATA] 涨跌家数来自乐咕: 涨 {up_count} 跌 {down_count}")
        except Exception as e:
            print(f"[WARN] 乐咕乐股接口失败: {e}")

    # 方案4：全A行情兜底
    if up_source == "none":
        try:
            spot_df = fetch_all_stock_spot()
            if not spot_df.empty and "涨跌幅" in spot_df.columns:
                pct = pd.to_numeric(spot_df["涨跌幅"], errors="coerce").dropna()
                up_count   = int((pct > 0).sum())
                down_count = int((pct < 0).sum())
                flat_count = int((pct == 0).sum())
                if up_count > 0 or down_count > 0:
                    up_source = "spot"
                    print(f"[DATA] 涨跌家数来自全A行情: 涨 {up_count} 跌 {down_count}")
        except Exception as e:
            print(f"[WARN] 全A行情接口失败: {e}")

    # ---------- 昨日涨停表现 ----------
    yesterday_perf = {
        "avg_pct": yesterday_avg_pct,
        "sample_count": 0,
        "promote_rate": promote_rate,
    }
    if yesterday_perf["avg_pct"] == 0:
        try:
            prev_df = safe_call(ak.stock_zt_pool_previous_em, date=date_str)
            if not prev_df.empty and "涨跌幅" in prev_df.columns:
                pcts = pd.to_numeric(prev_df["涨跌幅"], errors="coerce").dropna()
                if len(pcts):
                    yesterday_perf["avg_pct"] = round(float(pcts.mean()), 2)
                    yesterday_perf["sample_count"] = int(len(pcts))
                    print(f"[DATA] 昨日涨停表现来自 AKShare: 均涨 {yesterday_perf['avg_pct']}%")
        except Exception as e:
            print(f"[WARN] 昨日涨停表现计算失败: {e}")

    # ---------- 按题材分组的连板梯队（开盘啦优先） ----------
    theme_groups = None

    # 方案1：开盘啦板块连板梯队
    kpl_sector = kpl_fetch_sector_ladder(date_str)
    if kpl_sector:
        theme_groups = build_theme_groups_from_kpl(kpl_sector, zt_df)
        if theme_groups:
            print(f"[KPL] 使用开盘啦题材分组，共 {len(theme_groups)} 个题材")

    # 方案2：按 industry 字段分组
    if not theme_groups:
        theme_groups = []
        if not zt_df.empty and "industry" in zt_df.columns:
            tmp = zt_df.copy()
            if "consecutive_days" in tmp.columns:
                tmp["consecutive_days"] = pd.to_numeric(
                    tmp["consecutive_days"], errors="coerce"
                ).fillna(1).astype(int)
            else:
                tmp["consecutive_days"] = 1
            tmp["_status"] = tmp.apply(_status_of, axis=1)
            tmp["_theme"] = tmp["industry"].fillna("其他").astype(str)

            for theme, grp in tmp.groupby("_theme"):
                stocks = []
                for _, row in grp.sort_values(
                    by=["first_seal_time", "consecutive_days"],
                    ascending=[True, False]
                ).iterrows():
                    try:
                        pct = float(row.get("pct_chg", 0) or 0)
                    except (ValueError, TypeError):
                        pct = 0.0
                    stocks.append({
                        "time": str(row.get("first_seal_time", "") or ""),
                        "name": str(row.get("name", "") or ""),
                        "code": str(row.get("code", "") or ""),
                        "lb": int(row.get("consecutive_days") or 1),
                        "status": str(row.get("_status") or ""),
                        "pct": pct,
                    })
                theme_groups.append({
                    "theme": theme, "count": len(stocks), "stocks": stocks,
                })
            theme_groups.sort(key=lambda g: (-g["count"], g["theme"]))
            print(f"[CONCEPT] 降级为 industry 分组，共 {len(theme_groups)} 组")

    sentiment = compute_sentiment_metrics({
        "zt_count": zt_count, "dt_count": dt_count, "zb_count": zb_count,
        "up_count": up_count, "down_count": down_count, "flat_count": flat_count,
        "break_rate": break_rate,
        "yesterday_zt_perf": yesterday_perf,
        "lianban_tiers": lianban_tiers,
    })
    return {
        "date": date_str,
        "prev_date": prev_trade_date(date_str),
        "zt_count": zt_count,
        "dt_count": dt_count,
        "zb_count": zb_count,
        "break_rate": break_rate,
        "up_count": up_count,
        "down_count": down_count,
        "flat_count": flat_count,
        "up_source": up_source,
        "lianban_tiers": lianban_tiers,
        "theme_dist": theme_dist,
        "yesterday_zt_perf": yesterday_perf,
        "sentiment": sentiment,
    }


def _market_prefix(code):
    """根据代码判断市场前缀（腾讯接口用）"""
    c = str(code)
    if c.startswith(("4", "8")):
        return "bj"
    if c.startswith(("0", "2", "3")):
        return "sz"
    return "sh"


_TX_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://gu.qq.com/",
}


def fetch_stock_minute(code):
    """个股分时（腾讯接口）"""
    try:
        symbol = _market_prefix(code) + str(code)
        url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query"
        r = requests.get(url, params={"code": symbol}, headers=_TX_HEADERS, timeout=8)
        j = r.json()
        d = j.get("data", {}).get(symbol, {}).get("data", {}).get("data") or []
        rows = []
        for line in d:
            parts = line.split()
            if len(parts) < 3:
                continue
            t = parts[0]
            time_str = f"{t[:2]}:{t[2:4]}"
            rows.append({
                "time": time_str,
                "price": float(parts[1]),
                "volume": int(parts[2]),
            })
        print(f"[TX] 分时 {symbol}: {len(rows)} 条")
        return rows
    except Exception as e:
        print(f"[WARN] 分时获取失败 {code}: {e}")
        return []


def fetch_stock_kline(code, days=120):
    """个股日K线（前复权，腾讯接口）"""
    try:
        symbol = _market_prefix(code) + str(code)
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {"param": f"{symbol},day,,,{days},qfq"}
        r = requests.get(url, params=params, headers=_TX_HEADERS, timeout=8)
        j = r.json()
        d = j.get("data", {}).get(symbol, {})
        kline = d.get("qfqday") or d.get("day") or []
        rows = []
        for item in kline:
            if len(item) < 6:
                continue
            rows.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]),
            })
        print(f"[TX] K线 {symbol}: {len(rows)} 条")
        return rows
    except Exception as e:
        print(f"[WARN] K线获取失败 {code}: {e}")
        return []


def fetch_stock_bid_ask(code):
    """五档盘口 + 实时报价（腾讯接口）"""
    try:
        symbol = _market_prefix(code) + str(code)
        url = f"https://qt.gtimg.cn/q={symbol}"
        r = requests.get(url, headers=_TX_HEADERS, timeout=8)
        r.encoding = "gbk"
        text = r.text.strip()
        if "=" not in text:
            return {}
        raw = text.split("=", 1)[1].strip().strip('";')
        f = raw.split("~")
        if len(f) < 50:
            return {}

        def _f(i, default=None):
            try:
                return float(f[i])
            except Exception:
                return default

        result = {
            "名称": f[1],
            "最新": _f(3),
            "昨收": _f(4),
            "今开": _f(5),
            "成交量手": _f(6),
            "涨跌": _f(31),
            "涨幅": _f(32),
            "最高": _f(33),
            "最低": _f(34),
            "成交量": _f(36),
            "成交额万": _f(37),
            "换手率": _f(38),
            "振幅": _f(43),
            "流通市值亿": _f(44),
            "总市值亿": _f(45),
            "市净率": _f(46),
            "涨停价": _f(47),
            "跌停价": _f(48),
            "量比": _f(49),
        }
        # 买卖五档
        for i in range(5):
            bp_idx = 9 + i * 2
            sp_idx = 19 + i * 2
            result[f"买{i+1}价"] = _f(bp_idx)
            result[f"买{i+1}量"] = _f(bp_idx + 1)
            result[f"卖{i+1}价"] = _f(sp_idx)
            result[f"卖{i+1}量"] = _f(sp_idx + 1)
        return {k: v for k, v in result.items() if v is not None}
    except Exception as e:
        print(f"[WARN] 盘口获取失败 {code}: {e}")
        return {}


def fetch_stock_zt_history(code, days=60):
    """历史涨停记录：遍历最近 N 个交易日的涨停池"""
    cache_file = os.path.join(CACHE_DIR, f"zt_history_{code}.json")
    today_str = datetime.now().strftime("%Y%m%d")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("updated_date") == today_str:
                return cache.get("records", [])
        except Exception:
            pass

    records = []
    try:
        trade_dates = get_trade_dates()
        recent = [d for d in trade_dates if d <= today_str][-days:]
        for d in recent:
            try:
                pool = ak.stock_zt_pool_em(date=d)
                if pool is None or pool.empty or "代码" not in pool.columns:
                    continue
                hit = pool[pool["代码"].astype(str) == str(code)]
                for _, row in hit.iterrows():
                    records.append({
                        "date": d,
                        "date_fmt": f"{d[2:4]}-{d[4:6]}-{d[6:8]}",
                        "lb": int(row.get("连板数", 1) or 1),
                        "industry": str(row.get("所属行业", "") or ""),
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] 历史涨停遍历失败: {e}")

    records.sort(key=lambda r: r["date"], reverse=True)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"updated_date": today_str, "records": records}, f, ensure_ascii=False)
    except Exception:
        pass
    return records


def kpl_fetch_sector_ladder(date_str):
    """拉取开盘啦板块连板梯队"""
    crawler = get_kpl_crawler()
    if not crawler:
        return None
    try:
        d = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        # 先试 YYYY-MM-DD，失败改 YYYYMMDD
        try:
            res = crawler.get_sector_limit_up_ladder(date=date_str)
        except Exception:
            res = crawler.get_sector_limit_up_ladder(date=d)
        if res and res.get("sectors"):
            print(f"[KPL] 题材板块 {len(res['sectors'])} 个")
            return res
        print("[KPL] 题材板块为空，降级行业分组")
    except Exception as e:
        print(f"[WARN] 开盘啦板块梯队失败: {e}")
    return None


def _status_of(row):
    """根据涨停池行判断开板状态"""
    t = str(row.get("first_seal_time", "") or "")
    try:
        bc = int(row.get("break_count", 0) or 0)
    except (ValueError, TypeError):
        bc = 0
    if t.startswith("09:25") and bc == 0:
        return "一字板"
    if bc == 0:
        return "未开板"
    return "换手板"


def build_theme_groups_from_kpl(sector_data, zt_df):
    """用开盘啦板块数据构建 theme_groups，与前端 renderLianbanBoard 兼容"""
    if not sector_data or not sector_data.get("sectors"):
        return None

    # 涨停池 code -> row 映射，用来补充首封时间、炸板次数等
    detail_map = {}
    if zt_df is not None and not zt_df.empty and "code" in zt_df.columns:
        for _, row in zt_df.iterrows():
            code = str(row.get("code", "") or "").strip()
            if code:
                detail_map[code] = row

    groups = []
    covered = set()

    for sector in sector_data.get("sectors", []):
        theme_name = str(sector.get("sector_name") or "其他").strip()
        stocks = []
        for s in sector.get("stocks", []):
            code = str(s.get("stock_code", "") or "")
            name = str(s.get("stock_name", "") or "")
            try:
                lb = int(s.get("consecutive_days", 1) or 1)
            except (ValueError, TypeError):
                lb = 1
            covered.add(code)

            row = detail_map.get(code)
            time_str, status, pct = "", "", 0.0
            if row is not None:
                time_str = str(row.get("first_seal_time", "") or "")
                status = _status_of(row)
                try:
                    pct = float(row.get("pct_chg", 0) or 0)
                except (ValueError, TypeError):
                    pct = 0.0

            stocks.append({
                "time": time_str, "name": name, "code": code,
                "lb": lb, "status": status, "pct": pct,
            })
        if stocks:
            stocks.sort(key=lambda x: (x["time"] or "99:99"))
            groups.append({"theme": theme_name, "count": len(stocks), "stocks": stocks})

    # 把不在任何题材里的股票归入"其他"
    if zt_df is not None and not zt_df.empty and "code" in zt_df.columns:
        others = []
        for _, row in zt_df.iterrows():
            code = str(row.get("code", "") or "").strip()
            if code and code not in covered:
                try:
                    lb = int(pd.to_numeric(row.get("consecutive_days", 1), errors="coerce") or 1)
                except (ValueError, TypeError):
                    lb = 1
                try:
                    pct = float(row.get("pct_chg", 0) or 0)
                except (ValueError, TypeError):
                    pct = 0.0
                others.append({
                    "time": str(row.get("first_seal_time", "") or ""),
                    "name": str(row.get("name", "") or ""),
                    "code": code, "lb": lb,
                    "status": _status_of(row), "pct": pct,
                })
        if others:
            others.sort(key=lambda x: (x["time"] or "99:99"))
            groups.append({"theme": "其他", "count": len(others), "stocks": others})

    groups.sort(key=lambda g: (-g["count"], g["theme"]))
    return groups


def get_stock_detail(code, date_str=None):
    """个股详情聚合"""
    if date_str is None:
        date_str = get_latest_trade_date()

    reason = ""
    try:
        zt_df = fetch_limit_up_pool(date_str)
        if not zt_df.empty and "code" in zt_df.columns:
            hit = zt_df[zt_df["code"].astype(str) == str(code)]
            if not hit.empty:
                row = hit.iloc[0]
                reason = str(row.get("reason") or row.get("industry") or "")
    except Exception as e:
        print(f"[WARN] 获取涨停原因失败: {e}")

    return {
        "code": str(code),
        "date": date_str,
        "minute": fetch_stock_minute(code),
        "kline": fetch_stock_kline(code, 120),
        "bid_ask": fetch_stock_bid_ask(code),
        "zt_history": fetch_stock_zt_history(code, 60),
        "reason": reason,
    }


def get_lhb_rich_data(date_str):
    """龙虎榜富数据：区分当日榜/三日榜；顶栏汇总 = 全部去重"""
    df = fetch_dragon_tiger(date_str)
    if df.empty:
        return {
            "date": date_str,
            "summary": {
                "total_stocks": 0, "total_lhb": 0, "total_net_buy": 0,
                "institution_count": 0, "top3": [],
                "today": {"total_stocks": 0, "total_net_buy": 0},
                "three_day": {"total_stocks": 0, "total_net_buy": 0},
            },
            "today_stocks": [],
            "three_day_stocks": [],
        }

    # 机构列表
    jg_codes = set()
    try:
        jg_df = _retry_call(ak.stock_lhb_jgmmtj_em, start_date=date_str, end_date=date_str, retry=3, delay=1.5)
        if jg_df is not None and not jg_df.empty and "代码" in jg_df.columns:
            jg_codes = set(jg_df["代码"].astype(str).tolist())
    except Exception as e:
        print(f"[WARN] 机构统计获取失败: {e}")

    def _f(v):
        try:
            return float(v) if v is not None and v != "" else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _is_3day(reason):
        r = str(reason or "")
        return ("连续三个交易日" in r or "连续3个交易日" in r
                or "三个交易日内" in r or "连续三个" in r)

    # 全部股票（去重，用于顶栏汇总）
    all_grouped = {}
    # 分组（同一股票可能同时出现在两个组）
    today_grouped = {}
    three_grouped = {}

    for _, row in df.iterrows():
        code = str(row.get("code", "") or "").strip()
        if not code:
            continue
        reason = str(row.get("reason", "") or "").strip()
        net = _f(row.get("net_buy", 0))

        # 全部去重（只取第一行的净买，不累加）
        if code not in all_grouped:
            all_grouped[code] = {
                "code": code,
                "name": str(row.get("name", "") or ""),
                "pct_chg": _f(row.get("pct_chg", 0)),
                "net_buy": net,
            }

        # 分类归档
        is_3day = _is_3day(reason)
        target = three_grouped if is_3day else today_grouped
        if code not in target:
            target[code] = {
                "code": code,
                "name": str(row.get("name", "") or ""),
                "pct_chg": _f(row.get("pct_chg", 0)),
                "net_buy": net,
                "buy_amount": _f(row.get("buy_amount", 0)),
                "sell_amount": _f(row.get("sell_amount", 0)),
                "reasons": [],
                "tags": [],
            }
        if reason and reason not in target[code]["reasons"]:
            target[code]["reasons"].append(reason)

    def finalize(grouped):
        stocks = list(grouped.values())
        for s in stocks:
            s["reason"] = " · ".join(s["reasons"])
            s.pop("reasons", None)
            if s["code"] in jg_codes:
                s["tags"].append("机构")
            # 游资标签改为前端展开明细时按营业部名称匹配 YZ_MAP 动态添加
            # 避免"净买入"就误标为游资
            s["tags"] = list(dict.fromkeys(s["tags"]))
        stocks.sort(key=lambda x: -x["net_buy"])
        return stocks

    today_stocks = finalize(today_grouped)
    three_stocks = finalize(three_grouped)

    # ---------- 顶栏汇总（全部去重口径） ----------
    all_list = sorted(all_grouped.values(), key=lambda x: -x["net_buy"])
    total_stocks = len(all_grouped)
    total_net_buy = sum(s["net_buy"] for s in all_grouped.values())
    institution_count = sum(1 for s in all_grouped.values() if s["code"] in jg_codes)
    top3 = [s["name"] for s in all_list[:3]]

    summary = {
        "total_stocks": total_stocks,
        "total_lhb": int(len(df)),
        "total_net_buy": total_net_buy,
        "institution_count": institution_count,
        "top3": top3,
        "today": {
            "total_stocks": len(today_stocks),
            "total_net_buy": sum(s["net_buy"] for s in today_stocks),
        },
        "three_day": {
            "total_stocks": len(three_stocks),
            "total_net_buy": sum(s["net_buy"] for s in three_stocks),
        },
        "all_stocks_count": total_stocks,
    }

    print(f"[LHB] {date_str}: 上榜 {total_stocks} 只（{len(df)} 条榜单）, "
          f"合计净买 {total_net_buy/1e8:.2f} 亿, 机构 {institution_count} 只 | "
          f"当日榜 {len(today_stocks)} 只, 三日榜 {len(three_stocks)} 只")

    return {
        "date": date_str,
        "summary": summary,
        "today_stocks": today_stocks,
        "three_day_stocks": three_stocks,
    }


def get_lhb_stock_detail(code, date_str):
    """个股龙虎榜买卖前5营业部"""
    result = {"buy": [], "sell": []}
    for flag, key in [("买入", "buy"), ("卖出", "sell")]:
        try:
            df = ak.stock_lhb_stock_detail_em(symbol=str(code), date=date_str, flag=flag)
            if df is None or df.empty:
                continue
            rows = []
            for _, r in df.head(5).iterrows():
                rows.append({
                    "yyb": str(r.get("交易营业部名称", "") or ""),
                    "buy": float(r.get("买入金额", 0) or 0),
                    "sell": float(r.get("卖出金额", 0) or 0),
                })
            result[key] = rows
        except Exception as e:
            print(f"[WARN] 明细获取失败 {code} {flag}: {e}")
    return result


_YOUZI_MAP_CACHE = None


def load_youzi_map():
    """从 static/youzi_map.json 读取游资名单（前后端共用）"""
    global _YOUZI_MAP_CACHE
    if _YOUZI_MAP_CACHE is not None:
        return _YOUZI_MAP_CACHE
    path = os.path.join("static", "youzi_map.json")
    if not os.path.exists(path):
        _YOUZI_MAP_CACHE = []
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _YOUZI_MAP_CACHE = [(it["name"], it.get("keywords", [])) for it in data]
        print(f"[YOUZI] 加载 {len(_YOUZI_MAP_CACHE)} 个游资")
    except Exception as e:
        print(f"[WARN] 读取 youzi_map.json 失败: {e}")
        _YOUZI_MAP_CACHE = []
    return _YOUZI_MAP_CACHE


# 营业部名里的噪音词（按长度从长到短依次去）
_YYB_NOISE = [
    "股份有限公司", "有限责任公司", "有限公司",
    "证券营业部", "证券营业厅", "营业部",
    "证券", "公司",
]


def _normalize_yyb(s):
    """去掉营业部名称中的噪音词，用于宽松匹配"""
    if not s:
        return ""
    t = str(s)
    for noise in _YYB_NOISE:
        t = t.replace(noise, "")
    return t


def match_youzi(yyb_name):
    """营业部名 → 游资名（归一化后子串匹配）"""
    if not yyb_name:
        return None
    raw = str(yyb_name)
    norm = _normalize_yyb(raw)
    for name, kws in load_youzi_map():
        for kw in kws:
            kw_norm = _normalize_yyb(kw)
            if not kw_norm:
                continue
            # 先试归一化匹配，再试原始子串匹配
            if kw_norm in norm or kw in raw:
                return name
    return None


def _merge_stock_entries(entries):
    """同一只股票多条记录合并"""
    by_code = {}
    for e in entries:
        code = e["code"]
        if code not in by_code:
            by_code[code] = {"code": code, "name": e["name"], "amount": 0.0}
        by_code[code]["amount"] += e["amount"]
    return sorted(by_code.values(), key=lambda x: -x["amount"])


def get_youzi_trace(date_str, use_cache=True):
    """游资追踪：按游资聚合当日买入/卖出股票"""
    cache_file = os.path.join(CACHE_DIR, f"youzi_trace_{date_str}.json")
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 1) 当日 + 三日榜股票（去重）
    lhb = get_lhb_rich_data(date_str)
    all_stocks = (lhb.get("today_stocks") or []) + (lhb.get("three_day_stocks") or [])
    seen = set()
    unique = []
    for s in all_stocks:
        if s.get("code") and s["code"] not in seen:
            seen.add(s["code"])
            unique.append(s)

    print(f"[YOUZI] {date_str}: 处理 {len(unique)} 只上榜股票")

    # 2) 并发拉取每只股票的明细
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_detail(stock):
        try:
            d = get_lhb_stock_detail(stock["code"], date_str)
            return stock, d
        except Exception as e:
            print(f"[WARN] {stock['code']} 明细失败: {e}")
            return stock, {"buy": [], "sell": []}

    details = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_fetch_detail, s) for s in unique]
        for fut in as_completed(futures):
            details.append(fut.result())

    # 3) 按游资聚合
    youzi_agg = {}

    def _add(yz, side, code, name, amount):
        if amount <= 0:
            return
        e = youzi_agg.setdefault(yz, {
            "buys": [], "sells": [],
            "buy_total": 0.0, "sell_total": 0.0,
            "buy_count": 0, "sell_count": 0,
        })
        if side == "buy":
            e["buys"].append({"code": code, "name": name, "amount": amount})
            e["buy_total"] += amount
            e["buy_count"] += 1
        else:
            e["sells"].append({"code": code, "name": name, "amount": amount})
            e["sell_total"] += amount
            e["sell_count"] += 1

    for stock, detail in details:
        code, name = stock["code"], stock["name"]
        for r in (detail.get("buy") or []):
            yz = match_youzi(r.get("yyb"))
            if yz:
                _add(yz, "buy", code, name, float(r.get("buy") or 0))
        for r in (detail.get("sell") or []):
            yz = match_youzi(r.get("yyb"))
            if yz:
                _add(yz, "sell", code, name, float(r.get("sell") or 0))

    result_list = []
    for name, e in youzi_agg.items():
        result_list.append({
            "name": name,
            "buy_total": e["buy_total"],
            "sell_total": e["sell_total"],
            "buy_count": e["buy_count"],
            "sell_count": e["sell_count"],
            "buys": _merge_stock_entries(e["buys"]),
            "sells": _merge_stock_entries(e["sells"]),
        })
    # 按买入额降序，卖出额次之
    result_list.sort(key=lambda x: (-x["buy_total"], -x["sell_total"]))

    result = {"date": date_str, "youzi": result_list}
    print(f"[YOUZI] {date_str}: 命中 {len(result_list)} 个游资")

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception as ex:
        print(f"[WARN] 缓存写入失败: {ex}")

    return result


def fetch_north_flow():
    """北向资金今日流向"""
    try:
        df = _retry_call(ak.stock_hsgt_fund_flow_summary_em, retry=2)
        if df is None or df.empty:
            return {}
        north = df[df["资金方向"] == "北向"] if "资金方向" in df.columns else df
        result = {"items": [], "total_net": 0.0}
        for _, r in north.iterrows():
            try:
                net = float(r.get("成交净买额", 0) or 0)
            except (ValueError, TypeError):
                net = 0
            item = {
                "type": str(r.get("类型", "") or ""),
                "board": str(r.get("板块", "") or ""),
                "net": net,
                "buy": float(r.get("买入成交额", 0) or 0),
                "sell": float(r.get("卖出成交额", 0) or 0),
            }
            result["items"].append(item)
            result["total_net"] += net
        print(f"[NORTH] 北向净买 {result['total_net']/1e8:+.2f}亿")
        return result
    except Exception as e:
        print(f"[WARN] 北向资金失败: {e}")
        return {}


def fetch_concept_flow(date_str=None, use_cache=True):
    """概念板块资金流向"""
    if not date_str:
        date_str = datetime.now().strftime("%Y%m%d")
    cache_file = os.path.join(CACHE_DIR, f"concept_flow_{date_str}.json")
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    result = {"inflow": [], "outflow": [], "all": []}

    def _load(symbol):
        try:
            df = ak.stock_fund_flow_concept(symbol=symbol)
            if df is None or df.empty:
                return None
            col_map = {"行业": "sector", "净额": "net_yi",
                       "行业-涨跌幅": "pct_chg", "领涨股": "leader",
                       "领涨股-涨跌幅": "leader_pct"}
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            if "sector" not in df.columns or "net_yi" not in df.columns:
                return None
            df["net_yi"] = pd.to_numeric(df["net_yi"], errors="coerce")
            return df.dropna(subset=["net_yi"]).reset_index(drop=True)
        except Exception:
            return None

    df_today = _load("即时")
    if df_today is None or df_today.empty:
        return result
    df_5d = _load("5日排行")

    merged = df_today.rename(columns={"net_yi": "main_net_yi"})[
        ["sector", "main_net_yi"] + [c for c in ["pct_chg", "leader", "leader_pct"] if c in df_today.columns]]
    if df_5d is not None and not df_5d.empty:
        tmp = df_5d[["sector", "net_yi"]].rename(columns={"net_yi": "net_5d_yi"})
        merged = merged.merge(tmp, on="sector", how="left")
    merged = merged.sort_values("main_net_yi", ascending=False).reset_index(drop=True)

    def _r(r):
        v1 = float(r["main_net_yi"]) * 1e8 if not pd.isna(r["main_net_yi"]) else 0
        v5 = float(r.get("net_5d_yi")) * 1e8 if "net_5d_yi" in r and not pd.isna(r.get("net_5d_yi")) else 0
        return {
            "sector": str(r["sector"]),
            "main_net": v1, "main_net_5d": v5,
            "pct_chg": float(r["pct_chg"]) if "pct_chg" in r and not pd.isna(r["pct_chg"]) else None,
            "leader": str(r.get("leader") or ""),
            "signal": _signal_of(v1, v5),
        }

    rows = [_r(r) for _, r in merged.iterrows()]
    result["inflow"] = rows[:8]
    result["outflow"] = rows[-8:][::-1]
    result["all"] = rows
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception:
        pass
    print(f"[CONCEPT] 概念板块 {len(rows)} 个")
    return result


def fetch_sector_stocks(sector_name, sector_type="industry"):
    """获取板块成分股（按涨幅降序，返回 Top15）"""
    try:
        if sector_type == "industry":
            df = ak.stock_board_industry_cons_em(symbol=sector_name)
        else:
            df = ak.stock_board_concept_cons_em(symbol=sector_name)
        if df is None or df.empty:
            return []
        df = df.copy()
        pct_col = "涨跌幅" if "涨跌幅" in df.columns else None
        if pct_col:
            df[pct_col] = pd.to_numeric(df[pct_col], errors="coerce")
            df = df.sort_values(pct_col, ascending=False)
        rows = []
        for _, r in df.head(15).iterrows():
            rows.append({
                "code": str(r.get("代码", "") or ""),
                "name": str(r.get("名称", "") or ""),
                "price": float(r.get("最新价", 0) or 0),
                "pct_chg": float(r.get(pct_col, 0) or 0) if pct_col else 0,
                "turnover": float(r.get("换手率", 0) or 0),
                "amount": float(r.get("成交额", 0) or 0),
            })
        print(f"[SECTOR-STOCKS] {sector_name}: {len(rows)} 只")
        return rows
    except Exception as e:
        print(f"[WARN] 板块成分股 {sector_name} 失败: {str(e)[:100]}")
        return []


def fetch_sector_trend(sector_name, days=30):
    """板块历史趋势（从累积 history 读）"""
    hist_file = os.path.join(CACHE_DIR, "sector_flow_history.json")
    if not os.path.exists(hist_file):
        return []
    try:
        with open(hist_file, "r", encoding="utf-8") as f:
            hist = json.load(f)
    except Exception:
        return []
    dates = sorted(hist.keys())[-days:]
    return [{"date": d, "net": hist[d].get(sector_name, 0)} for d in dates
            if sector_name in hist.get(d, {})]


def _pick_col(df, keywords):
    """从 DataFrame 中找到名称包含任意关键词的列"""
    for col in df.columns:
        for kw in keywords:
            if kw in str(col):
                return col
    return None


def _pick_col(df, keywords):
    for col in df.columns:
        for kw in keywords:
            if kw in str(col):
                return col
    return None


def _load_rank(symbol):
    """拉取指定排行的行业资金流，返回 DataFrame [sector, net_yi, pct, leader, leader_pct]"""
    try:
        df = ak.stock_fund_flow_industry(symbol=symbol)
        if df is None or df.empty:
            return None
        col_map = {
            "行业": "sector",
            "净额": "net_yi",
            "行业-涨跌幅": "pct_chg",
            "领涨股": "leader",
            "领涨股-涨跌幅": "leader_pct",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "sector" not in df.columns or "net_yi" not in df.columns:
            print(f"[SECTOR] {symbol} 缺列: {list(df.columns)}")
            return None
        df["net_yi"] = pd.to_numeric(df["net_yi"], errors="coerce")
        if "pct_chg" in df.columns:
            df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
        df = df.dropna(subset=["net_yi"]).reset_index(drop=True)
        print(f"[SECTOR] {symbol}: {len(df)} 个行业")
        return df
    except Exception as e:
        print(f"[SECTOR] {symbol} 失败: {str(e)[:100]}")
        return None


def _signal_of(v1, v5):
    """基于今日和5日净流入给信号"""
    try:
        v1 = float(v1) if v1 is not None else 0
        v5 = float(v5) if v5 is not None else 0
    except (ValueError, TypeError):
        return ""
    if v1 > 0 and v5 > 0:
        return "加速流入" if v5 > v1 else "持续流入"
    if v1 < 0 and v5 < 0:
        return "加速流出" if abs(v5) > abs(v1) else "持续流出"
    if v1 > 0 and v5 <= 0:
        return "由流出转流入"
    if v1 < 0 and v5 >= 0:
        return "由流入转流出"
    return ""


SECTOR_HIST_FILE = os.path.join(CACHE_DIR, "sector_flow_history.json")


def fetch_sector_flow(date_str=None, use_cache=True):
    """板块资金流向（今日 + 3日/5日/10日 官方排行）"""
    if not date_str:
        from datetime import datetime as _dt
        date_str = _dt.now().strftime("%Y%m%d")

    cache_file = os.path.join(CACHE_DIR, f"sector_flow_{date_str}.json")
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    result = {
        "inflow": [], "outflow": [], "all": [],
        "rotation_signal": {"in": [], "out": []},
    }

    # 拉 4 个排行
    df_today = _load_rank("即时")
    if df_today is None or df_today.empty:
        print("[SECTOR] 即时排行失败，无法继续")
        return result

    df_3d = _load_rank("3日排行")
    df_5d = _load_rank("5日排行")
    df_10d = _load_rank("10日排行")

    # 合并
    merged = df_today[["sector", "net_yi"]].rename(columns={"net_yi": "main_net_yi"})
    for src, col in [(df_3d, "net_3d_yi"), (df_5d, "net_5d_yi"), (df_10d, "net_10d_yi")]:
        if src is not None and not src.empty:
            tmp = src[["sector", "net_yi"]].rename(columns={"net_yi": col})
            merged = merged.merge(tmp, on="sector", how="left")

    # 补充领涨股
    if "leader" in df_today.columns:
        merged = merged.merge(
            df_today[["sector"] + [c for c in ["pct_chg", "leader", "leader_pct"] if c in df_today.columns]],
            on="sector", how="left"
        )

    merged = merged.sort_values("main_net_yi", ascending=False).reset_index(drop=True)

    def _r(r):
        v1 = float(r["main_net_yi"]) * 1e8 if not pd.isna(r["main_net_yi"]) else 0
        v5 = float(r.get("net_5d_yi")) * 1e8 if not pd.isna(r.get("net_5d_yi")) else 0
        v3 = float(r.get("net_3d_yi")) * 1e8 if not pd.isna(r.get("net_3d_yi")) else 0
        v10 = float(r.get("net_10d_yi")) * 1e8 if not pd.isna(r.get("net_10d_yi")) else 0
        return {
            "sector": str(r["sector"]),
            "main_net": v1,
            "main_net_3d": v3,
            "main_net_5d": v5,
            "main_net_10d": v10,
            "pct_chg": float(r["pct_chg"]) if "pct_chg" in r and not pd.isna(r["pct_chg"]) else None,
            "leader": str(r.get("leader") or "") if "leader" in r else "",
            "leader_pct": float(r["leader_pct"]) if "leader_pct" in r and not pd.isna(r["leader_pct"]) else None,
            "signal": _signal_of(v1, v5),
        }

    rows = [_r(r) for _, r in merged.iterrows()]
    rows.sort(key=lambda x: -x["main_net"])

    result["inflow"] = rows[:6]
    result["outflow"] = rows[-6:][::-1]
    result["all"] = rows
    result["rotation_signal"] = {
        "in": [r["sector"] for r in rows[:3]],
        "out": [r["sector"] for r in rows[-3:]],
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception:
        pass

    print(f"[SECTOR] 完成：{len(rows)} 个行业，Top: {rows[0]['sector']} {rows[0]['main_net']/1e8:+.2f}亿 (5日 {rows[0]['main_net_5d']/1e8:+.2f}亿)")
    return result


def compute_sentiment_metrics(metrics):
    """基于市场指标计算赚钱/亏钱效应评分"""
    zt = int(metrics.get("zt_count", 0) or 0)
    dt = int(metrics.get("dt_count", 0) or 0)
    zb = int(metrics.get("zb_count", 0) or 0)
    up = int(metrics.get("up_count", 0) or 0)
    down = int(metrics.get("down_count", 0) or 0)
    flat = int(metrics.get("flat_count", 0) or 0)
    break_rate = float(metrics.get("break_rate", 0) or 0)

    yp = metrics.get("yesterday_zt_perf", {}) or {}
    promote_rate = float(yp.get("promote_rate", 0) or 0)
    avg_pct = float(yp.get("avg_pct", 0) or 0)

    tiers = metrics.get("lianban_tiers", {}) or {}
    max_lb = max([int(k) for k, v in tiers.items() if v], default=0)

    # ---- 派生指标 ----
    total = up + down + flat
    adr = (up / down) if down > 0 else (up if up > 0 else 0)
    up_ratio = (up / total * 100) if total > 0 else 50
    zt_dt_ratio = (zt / dt) if dt > 0 else (zt if zt > 0 else 0)

    # ---- 评分函数（0-100） ----
    def s_adr(v):
        if v >= 2:    return 100
        if v >= 1.5:  return 85
        if v >= 1:    return 70
        if v >= 0.67: return 45
        if v >= 0.5:  return 25
        return 10

    def s_up_ratio(v):
        return min(100, max(0, (v - 15) / 70 * 100))

    def s_break_rate(v):
        if v <= 15: return 100
        if v <= 25: return 75
        if v <= 35: return 50
        if v <= 45: return 30
        return 10

    def s_avg_pct(v):
        return min(100, max(0, (v + 3) / 6 * 100))

    def s_promote(v):
        if v >= 30: return 100
        if v >= 25: return 90
        if v >= 15: return 65
        if v >= 10: return 40
        return 15

    def s_lb(v):
        if v >= 6: return 100
        if v >= 5: return 85
        if v >= 4: return 70
        if v >= 3: return 55
        if v >= 2: return 35
        return 15

    def s_zt_dt(v):
        if v >= 5:   return 100
        if v >= 2:   return 80
        if v >= 1:   return 65
        if v >= 0.5: return 40
        return 15

    scores = {
        "adr":         s_adr(adr),
        "up_ratio":    s_up_ratio(up_ratio),
        "zt_dt":       s_zt_dt(zt_dt_ratio),
        "break_rate":  s_break_rate(break_rate),
        "avg_pct":     s_avg_pct(avg_pct),
        "promote":     s_promote(promote_rate),
        "lb_height":   s_lb(max_lb),
    }
    weights = {
        "avg_pct":    0.22,
        "promote":    0.18,
        "break_rate": 0.13,
        "lb_height":  0.13,
        "adr":        0.12,
        "up_ratio":   0.10,
        "zt_dt":      0.12,
    }
    total_score = sum(scores[k] * weights[k] for k in scores)

    def level_of(sc):
        if sc >= 75: return ("强赚钱", "strong-up")
        if sc >= 60: return ("偏强",   "up")
        if sc >= 45: return ("中性",   "neutral")
        if sc >= 30: return ("偏弱",   "down")
        return ("强亏钱", "strong-down")

    level_name, level_cls = level_of(total_score)

    def status(score):
        if score >= 70: return "good"
        if score >= 45: return "mid"
        return "bad"

    return {
        "score": round(total_score),
        "level": level_name,
        "level_cls": level_cls,
        "adr": round(adr, 2),
        "up_ratio": round(up_ratio, 1),
        "zt_dt_ratio": round(zt_dt_ratio, 2),
        "break_rate": round(break_rate, 2),
        "avg_pct": round(avg_pct, 2),
        "promote_rate": round(promote_rate, 2),
        "max_lb": max_lb,
        "items": [
            {"key": "avg_pct",     "label": "昨日涨停溢价", "value": f"{avg_pct:+.2f}%",  "score": scores["avg_pct"],    "status": status(scores["avg_pct"]),    "hint": "越高越好，>3%为强"},
            {"key": "promote",     "label": "连板晋级率",   "value": f"{promote_rate:.1f}%", "score": scores["promote"],   "status": status(scores["promote"]),    "hint": "越高越好，>25%为强"},
            {"key": "break_rate",  "label": "炸板率",       "value": f"{break_rate:.1f}%",  "score": scores["break_rate"], "status": status(scores["break_rate"]), "hint": "越低越好，<20%为强"},
            {"key": "lb_height",   "label": "最高连板",     "value": f"{max_lb}板",         "score": scores["lb_height"],  "status": status(scores["lb_height"]),  "hint": "越高越好，≥5板为强"},
            {"key": "zt_dt",       "label": "涨停/跌停比",  "value": f"{zt}/{dt}",          "score": scores["zt_dt"],      "status": status(scores["zt_dt"]),      "hint": "比值越高越好"},
            {"key": "adr",         "label": "涨跌家数比",   "value": f"{adr:.2f}",          "score": scores["adr"],        "status": status(scores["adr"]),        "hint": ">1.5偏强，<0.7偏弱"},
            {"key": "up_ratio",    "label": "上涨家数占比", "value": f"{up_ratio:.1f}%",    "score": scores["up_ratio"],   "status": status(scores["up_ratio"]),   "hint": ">60%偏强，<40%偏弱"},
        ],
    }


def _df_to_records(df, limit=None):
    if df is None or df.empty:
        return []
    d = df.head(limit) if limit else df
    return json.loads(d.to_json(orient="records", force_ascii=False, date_format="iso"))


def get_full_review(date_str=None, use_cache=True):
    if date_str is None:
        date_str = get_recent_trade_date()

    cache_file = os.path.join(CACHE_DIR, f"review_{date_str}.json")
    if use_cache and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    metrics = compute_market_metrics(date_str)
    zt_df = fetch_limit_up_pool(date_str)
    dt_df = fetch_limit_down_pool(date_str)
    zb_df = fetch_broken_pool(date_str)
    lhb_df = fetch_dragon_tiger(date_str)

    sector_flow = fetch_sector_flow(date_str, use_cache=use_cache)

    result = {
        "metrics": metrics,
        "sector_flow": sector_flow,
        "limit_up_stocks": _df_to_records(zt_df, 200),
        "limit_down_stocks": _df_to_records(dt_df, 100),
        "broken_stocks": _df_to_records(zb_df, 100),
        "dragon_tiger": _df_to_records(lhb_df, 100),
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] 缓存写入失败: {e}")

    return result


if __name__ == "__main__":
    data = get_full_review()
    print(json.dumps(data["metrics"], ensure_ascii=False, indent=2))


_TRADE_DATES_CACHE = None


def get_trade_dates():
    """获取全部交易日列表 (YYYYMMDD)，带内存缓存"""
    global _TRADE_DATES_CACHE
    if _TRADE_DATES_CACHE is not None:
        return _TRADE_DATES_CACHE
    df = safe_call(ak.tool_trade_date_hist_sina)
    if df.empty:
        _TRADE_DATES_CACHE = []
        return []
    dates = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d").tolist()
    _TRADE_DATES_CACHE = sorted(set(dates))
    return _TRADE_DATES_CACHE


def get_latest_trade_date():
    """获取今日或之前最近的一个交易日"""
    dates = get_trade_dates()
    today = datetime.now().strftime("%Y%m%d")
    if not dates:
        return get_recent_trade_date()
    past = [d for d in dates if d <= today]
    return past[-1] if past else dates[0]


# =====================================================
# 开盘啦爬虫集成
# =====================================================
_kpl_crawler = None


def get_kpl_crawler():
    """获取开盘啦爬虫实例（单例）"""
    global _kpl_crawler
    if _kpl_crawler is not None:
        return _kpl_crawler if _kpl_crawler is not False else None
    if KaipanlaCrawler is None:
        print("[KPL] kaipanla_crawler 未安装或导入失败，跳过")
        _kpl_crawler = False
        return None
    try:
        _kpl_crawler = KaipanlaCrawler()
        print("[KPL] 开盘啦爬虫实例已创建")
    except Exception as e:
        print(f"[WARN] 开盘啦爬虫初始化失败: {e}")
        _kpl_crawler = False
    return _kpl_crawler if _kpl_crawler else None


def kpl_fetch_daily_data(date_str):
    """获取开盘啦单日市场数据"""
    crawler = get_kpl_crawler()
    if not crawler:
        return None
    try:
        d = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        data = crawler.get_daily_data(d)
        if data is not None and not data.empty:
            print(f"[KPL] 获取到 {date_str} 市场数据")
            return data
    except Exception as e:
        print(f"[WARN] 开盘啦 get_daily_data 失败: {e}")
    return None


def kpl_fetch_limit_up_sectors(date_str):
    """获取涨停原因板块"""
    crawler = get_kpl_crawler()
    if not crawler:
        return None
    try:
        d = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        data = crawler.get_limit_up_sectors(d)
        if data:
            print(f"[KPL] 获取到涨停原因板块数据")
            return data
    except Exception as e:
        print(f"[WARN] 开盘啦 get_limit_up_sectors 失败: {e}")
    return None

