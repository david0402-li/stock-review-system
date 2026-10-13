# -*- coding: utf-8 -*-
"""
开盘啦爬虫HTTP接口服务
功能：将kaipanla_crawler.py的所有方法封装为HTTP接口
端口：8898
终极修复：Linux + curl 中文正常显示，无 Unicode 转义
"""
from flask import Flask, request, Response
import pandas as pd
from datetime import datetime
import uuid
import requests
import urllib3
import json
from typing import Optional, List, Dict

# ====================== 终极中文修复（强制不转义） ======================
app = Flask(__name__)

# 自定义 jsonify，强制中文输出
def jsonify_chinese(*args, **kwargs):
    json_str = json.dumps(
        kwargs, ensure_ascii=False, separators=(',', ':'), sort_keys=False
    )
    return Response(
        json_str,
        mimetype='application/json; charset=utf-8'
    )
# ======================================================================

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====================== 复用原爬虫核心代码 ======================
def is_weekend(date_str: str) -> bool:
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.weekday() >= 5
    except:
        return False

def get_trading_dates(start_date: str, end_date: str) -> List[str]:
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return []
    if start > end:
        start, end = end, start
    trading_dates = []
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        if not is_weekend(date_str):
            trading_dates.append(date_str)
        current += pd.Timedelta(days=1)
    return trading_dates

class KaipanlaCrawler:
    def __init__(self):
        self.base_url = "https://apphis.longhuvip.com/w1/api/index.php"
        self.sector_base_url = "https://apphwhq.longhuvip.com/w1/api/index.php"
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SHARK PRS-A0 Build/PQ3A.190605.01141736)",
            "Host": "apphis.longhuvip.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        self.sector_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SHARK PRS-A0 Build/PQ3A.190605.01141736)",
            "Host": "apphwhq.longhuvip.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }

    def _request(self, data_params: Dict, date: str, timeout: Optional[int] = 1600) -> Dict:
        params = {"apiv": "w42", "PhoneOSNew": "1", "VerSion": "5.21.0.2"}
        data = {
            "PhoneOSNew": "1",
            "DeviceID": str(uuid.uuid4()),
            "VerSion": "5.21.0.2",
            "apiv": "w42",
            "Day": date
        }
        data.update(data_params)
        try:
            response = requests.post(
                self.base_url,
                params=params,
                data=data,
                headers=self.headers,
                verify=False,
                proxies={'http': None, 'https': None},
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"请求失败 ({date}): {e}")
            return {}

    def _get_single_day_data(self, date: str) -> Dict:
        result1 = self._request({"a": "HisZhangFuDetail", "c": "HisHomeDingPan"}, date)
        info1 = result1.get("info", {}) if result1 else {}
        result2 = self._request({"a": "GetZsReal", "c": "StockL2History"}, date)
        stock_list = result2.get("StockList", []) if result2 else []
        sh_index = next((s for s in stock_list if s.get("StockID") == "SH000001"), None)
        result3 = self._request({"a": "ZhangTingExpression", "c": "HisHomeDingPan"}, date)
        info3 = result3.get("info", []) if result3 else []
        result4 = self._request({"a": "SharpWithdrawal", "c": "HisHomeDingPan"}, date)
        withdrawal_num = result4.get("num", 0) if result4 else 0

        return {
            "日期": result1.get("date", date) if result1 else date,
            "涨停数": int(info1.get("ZT", 0)),
            "实际涨停": int(info1.get("SJZT", 0)),
            "跌停数": int(info1.get("DT", 0)),
            "实际跌停": int(info1.get("SJDT", 0)),
            "上涨家数": int(info1.get("SZJS", 0)),
            "下跌家数": int(info1.get("XDJS", 0)),
            "平盘家数": int(info1.get("0", 0)),
            "上证指数": float(sh_index.get("last_px", 0)) if sh_index else 0,
            "最新价": float(sh_index.get("last_px", 0)) if sh_index else 0,
            "涨跌幅": sh_index.get("increase_rate", "") if sh_index else "",
            "成交额": int(sh_index.get("turnover", 0)) if sh_index else 0,
            "首板数量": info3[0] if len(info3) > 0 else 0,
            "2连板数量": info3[1] if len(info3) > 1 else 0,
            "3连板数量": info3[2] if len(info3) > 2 else 0,
            "4连板以上数量": info3[3] if len(info3) > 3 else 0,
            "连板率": round(info3[4], 2) if len(info3) > 4 else 0,
            "大幅回撤家数": withdrawal_num,
        }

    def get_daily_data(self, end_date: str, start_date: Optional[str] = None) -> pd.DataFrame | pd.Series:
        if start_date is None:
            data = self._get_single_day_data(end_date)
            return pd.Series(data)
        date_list = get_trading_dates(start_date, end_date)
        records = []
        for date in date_list:
            data = self._get_single_day_data(date)
            records.append(data)
        df = pd.DataFrame(records)
        df = df[df["涨停数"] > 0]
        return df

    def get_new_high_data(self, end_date: str, start_date: Optional[str] = None, timeout: Optional[int] = 1600) -> pd.Series:
        data = {
            "a": "GetDayNewHigh_W28",
            "st": "360",
            "c": "StockNewHigh",
            "PhoneOSNew": "1",
            "DeviceID": str(uuid.uuid4()),
            "VerSion": "5.21.0.2",
            "Index": "0",
            "GroupID": "ALL",
            "apiv": "w42",
            "Type": "0_0_0_0_0"
        }
        try:
            response = requests.post(self.base_url, data=data, headers=self.headers, verify=False, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            if not result or result.get("errcode") != "0":
                return pd.Series()
            x_data = result.get("x", [])
            if not x_data:
                return pd.Series()
            dates = []
            new_highs = []
            for item in x_data:
                parts = item.split("_")
                if len(parts) >= 3:
                    date_str = parts[0]
                    new_count = int(parts[2])
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    dates.append(formatted_date)
                    new_highs.append(new_count)
            series = pd.Series(new_highs, index=dates)
            series.index.name = "日期"
            series.name = "今日新增"
            if start_date is None:
                return series[end_date] if end_date in series.index else pd.Series()
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            if start > end:
                start, end = end, start
            mask = (pd.to_datetime(series.index) >= start) & (pd.to_datetime(series.index) <= end)
            return series[mask]
        except Exception as e:
            return pd.Series()

    def get_market_sentiment(self, date: Optional[str] = None) -> pd.DataFrame:
        if not date: date = datetime.now().strftime("%Y-%m-%d")
        result = self._request({"a": "HisZhangFuDetail", "c": "HisHomeDingPan"}, date)
        if not result: return pd.DataFrame()
        info = result.get("info", {})
        return pd.DataFrame({
            "日期": [result.get("date", date)],
            "涨停数": [int(info.get("ZT", 0))],
            "实际涨停": [int(info.get("SJZT", 0))],
            "跌停数": [int(info.get("DT", 0))],
            "实际跌停": [int(info.get("SJDT", 0))],
            "上涨家数": [int(info.get("SZJS", 0))],
            "下跌家数": [int(info.get("XDJS", 0))],
            "平盘家数": [int(info.get("0", 0))]
        })

    def get_market_index(self, date: Optional[str] = None) -> pd.DataFrame:
        if not date: date = datetime.now().strftime("%Y-%m-%d")
        result = self._request({"a": "GetZsReal", "c": "StockL2History"}, date)
        if not result: return pd.DataFrame()
        return pd.DataFrame([{
            "日期": date,
            "指数代码": s.get("StockID", ""),
            "指数名称": s.get("prod_name", ""),
            "最新价": float(s.get("last_px", 0)),
            "涨跌额": float(s.get("increase_amount", 0)),
            "涨跌幅": s.get("increase_rate", ""),
            "成交额(元)": int(s.get("turnover", 0))
        } for s in result.get("StockList", [])])

    def get_limit_up_ladder(self, date: Optional[str] = None) -> pd.DataFrame:
        if not date: date = datetime.now().strftime("%Y-%m-%d")
        result = self._request({"a": "ZhangTingExpression", "c": "HisHomeDingPan"}, date)
        if not result or len(result.get("info", [])) < 12:
            return pd.DataFrame()
        info = result.get("info", [])
        return pd.DataFrame({
            "日期": [date], "一板": [info[0]], "二板": [info[1]], "三板": [info[2]],
            "高度板": [info[3]], "连板率(%)": [round(info[4], 2)], "昨日首板今日上涨数": [info[5]],
            "昨日首板今日下跌数": [info[6]], "今日涨停破板率(%)": [round(info[7], 2)],
            "昨日涨停今表现(%)": [round(info[8], 2)], "昨日连板今表现(%)": [round(info[9], 2)],
            "昨日破板今表现(%)": [round(info[10], 2)], "市场评价": [info[11]]
        })

    def get_sharp_withdrawal(self, date: Optional[str] = None) -> pd.DataFrame:
        if not date: date = datetime.now().strftime("%Y-%m-%d")
        result = self._request({"a": "SharpWithdrawal", "c": "HisHomeDingPan"}, date)
        if not result: return pd.DataFrame()
        total_num = result.get("num", 0)
        return pd.DataFrame([{
            "日期": result.get("date", date), "股票代码": i[0], "股票名称": i[1],
            "当日涨跌幅(%)": round(i[2], 2), "回撤幅度(%)": round(i[3], 2),
            "最新价": round(i[4], 2), "总数": total_num
        } for i in result.get("info", []) if len(i) >= 5])

    def get_sector_ranking(self, date: Optional[str] = None, index: int = 0, timeout: Optional[int] = 1600) -> Dict:
        if not date: date = datetime.now().strftime("%Y-%m-%d")
        data = {
            "a": "GetPlateInfo_w38", "st": "100", "c": "DailyLimitResumption",
            "PhoneOSNew": "1", "DeviceID": str(uuid.uuid4()), "VerSion": "5.21.0.2",
            "Index": str(index), "apiv": "w42", "Day": date
        }
        try:
            response = requests.post(self.sector_base_url, data=data, headers=self.sector_headers, verify=False, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            if not result or result.get("errcode") != "0":
                return {"summary": {}, "sectors": []}
            nums = result.get("nums", {})
            summary = {
                "日期": result.get("date", date), "上涨家数": nums.get("SZJS", 0),
                "下跌家数": nums.get("XDJS", 0), "涨停数": nums.get("ZT", 0),
                "跌停数": nums.get("DT", 0), "涨跌比": round(nums.get("ZBL", 0), 2),
                "昨日涨跌比": round(nums.get("yestRase", 0), 2)
            }
            sectors = []
            for sd in result.get("list", []):
                si = {
                    "sector_code": sd.get("ZSCode", ""), "sector_name": sd.get("ZSName", ""),
                    "stock_count": sd.get("num", 0), "stocks": []
                }
                for s in sd.get("StockList", []):
                    if len(s) >= 19:
                        si["stocks"].append({
                            "股票代码": s[0], "股票名称": s[1], "涨停价": s[4],
                            "流通市值(元)": s[8], "连板天数": s[9], "连板次数": s[10],
                            "概念标签": s[11], "封单额(元)": s[12], "主力资金(元)": s[13],
                            "首次封板时间": s[14], "总市值(元)": s[15], "涨停原因": s[16],
                            "主题": s[17], "是否首板": s[18]
                        })
                sectors.append(si)
            return {"summary": summary, "sectors": sectors}
        except:
            return {"summary": {}, "sectors": []}

# ====================== HTTP 接口（全部替换为中文输出） ======================
crawler = KaipanlaCrawler()

@app.route('/api/daily_data', methods=['GET', 'POST'])
def api_daily_data():
    try:
        end_date = request.values.get('end_date')
        start_date = request.values.get('start_date')
        if not end_date:
            return jsonify_chinese(code=400, msg="end_date参数必传", data=None)
        if start_date:
            df = crawler.get_daily_data(end_date, start_date)
            data = df.to_dict('records')
        else:
            series = crawler.get_daily_data(end_date)
            data = series.to_dict()
        return jsonify_chinese(code=200, msg="success", data=data)
    except Exception as e:
        return jsonify_chinese(code=500, msg=str(e), data=None)

@app.route('/api/new_high_data', methods=['GET', 'POST'])
def api_new_high_data():
    try:
        end_date = request.values.get('end_date')
        start_date = request.values.get('start_date')
        if not end_date:
            return jsonify_chinese(code=400, msg="end_date参数必传", data=None)
        series = crawler.get_new_high_data(end_date, start_date)
        data = series.to_dict() if start_date else (series if not series.empty else 0)
        return jsonify_chinese(code=200, msg="success", data=data)
    except Exception as e:
        return jsonify_chinese(code=500, msg=str(e), data=None)

@app.route('/api/market_sentiment', methods=['GET', 'POST'])
def api_market_sentiment():
    try:
        date = request.values.get('date', datetime.now().strftime("%Y-%m-%d"))
        df = crawler.get_market_sentiment(date)
        return jsonify_chinese(code=200, msg="success", data=df.to_dict('records') if not df.empty else [])
    except:
        return jsonify_chinese(code=500, msg="异常", data=[])

@app.route('/api/market_index', methods=['GET', 'POST'])
def api_market_index():
    try:
        date = request.values.get('date', datetime.now().strftime("%Y-%m-%d"))
        df = crawler.get_market_index(date)
        return jsonify_chinese(code=200, msg="success", data=df.to_dict('records') if not df.empty else [])
    except:
        return jsonify_chinese(code=500, msg="异常", data=[])

@app.route('/api/limit_up_ladder', methods=['GET', 'POST'])
def api_limit_up_ladder():
    try:
        date = request.values.get('date', datetime.now().strftime("%Y-%m-%d"))
        df = crawler.get_limit_up_ladder(date)
        return jsonify_chinese(code=200, msg="success", data=df.to_dict('records') if not df.empty else [])
    except:
        return jsonify_chinese(code=500, msg="异常", data=[])

@app.route('/api/sharp_withdrawal', methods=['GET', 'POST'])
def api_sharp_withdrawal():
    try:
        date = request.values.get('date', datetime.now().strftime("%Y-%m-%d"))
        df = crawler.get_sharp_withdrawal(date)
        return jsonify_chinese(code=200, msg="success", data=df.to_dict('records') if not df.empty else [])
    except:
        return jsonify_chinese(code=500, msg="异常", data=[])

@app.route('/api/sector_ranking', methods=['GET', 'POST'])
def api_sector_ranking():
    try:
        date = request.values.get('date', datetime.now().strftime("%Y-%m-%d"))
        index = int(request.values.get('index', 0))
        data = crawler.get_sector_ranking(date, index)
        return jsonify_chinese(code=200, msg="success", data=data)
    except:
        return jsonify_chinese(code=500, msg="异常", data={"summary":{},"sectors":[]})

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify_chinese(code=200, msg="服务运行正常", timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# ====================== 启动 ======================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8898, debug=False)