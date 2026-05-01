# agent/data_engine.py
# v5.5 - 修复成交量数据缺失，支持实时与均量抓取

import logging
import os
import time
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


# ── 自定义 API 引擎 ────────────────────────────────────────────────────────────

def _fetch_fear_greed() -> Optional[dict]:
    """通过 Alternative.me 抓取恐慌与贪婪指数"""
    url = "https://api.alternative.me/fng/"
    try:
        import requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        val = int(data['data'][0]['value'])
        status = data['data'][0]['value_classification']
        
        return {
            "name":       "恐惧与贪婪指数",
            "price":      val,
            "change_pct": 0.0,
            "volume":     0,
            "avg_volume": 0,
            "note":       status
        }
    except Exception as e:
        logger.warning("恐惧与贪婪指数抓取失败: %s", e)
        return None

def _fetch_fred(series_id: str, name: str) -> Optional[dict]:
    """通过官方 FRED API 抓取宏观数据"""
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        logger.warning("FRED_API_KEY 未设置，跳过 %s 抓取", name)
        return None
        
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
    try:
        import requests
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("observations", [])
        
        if len(data) < 2:
            return None
            
        valid_vals = [float(d["value"]) for d in data if d["value"] != "."][:2]
        if len(valid_vals) < 2:
            return None
            
        val_today = valid_vals[0]
        val_prev = valid_vals[1]
        change_pct = (val_today - val_prev) / val_prev * 100
        
        return {
            "name":       name,
            "price":      val_today,
            "change_pct": change_pct,
            "volume":     0,
            "avg_volume": 0,
            "note":       ""
        }
    except Exception as e:
        logger.warning("FRED 抓取失败 [%s]: %s", series_id, e)
        return None


# ── 公共接口：市场状态 ─────────────────────────────────────────────────────────

def market_status() -> dict:
    """查询当前市场状态。"""
    weekday = date.today().weekday()
    if weekday == 5:
        return {"is_trading_day": False, "is_open": False,
                "note": "⚠️ 今日周六，数据为上一交易日收盘"}
    if weekday == 6:
        return {"is_trading_day": False, "is_open": False,
                "note": "⚠️ 今日周日，数据为上一交易日收盘"}

    api_key = os.environ.get("FINNHUB_API_KEY")
    if api_key:
        try:
            import finnhub
            client = finnhub.Client(api_key=api_key)
            status = client.market_status(exchange="US")
            holiday = status.get("holiday")
            is_open = status.get("isOpen", False)

            if holiday:
                return {
                    "is_trading_day": False,
                    "is_open":        False,
                    "note":           f"⚠️ 今日休市（{holiday}），数据为上一交易日收盘",
                }
            return {"is_trading_day": True, "is_open": is_open, "note": ""}
        except Exception as e:
            logger.warning("Finnhub market_status 查询失败：%s", e)

    # 兜底默认设为休市，防止 API 失败导致无效扫描
    return {"is_trading_day": True, "is_open": False, "note": "接口查询异常"}


# ── 公共接口：股票数据 ─────────────────────────────────────────────────────────

def fetch(tickers: list) -> dict:
    """统一数据出口。"""
    results = {}
    finnhub_tickers = []
    
    for sym, name in tickers:
        if sym == "FNG":
            results[sym] = _fetch_fear_greed()
        elif sym == "DGS10":
            results[sym] = _fetch_fred(sym, name)
        else:
            finnhub_tickers.append((sym, name))
            
    if finnhub_tickers:
        results.update(_from_finnhub(finnhub_tickers))
        
    return results


# ── Finnhub 引擎 ───────────────────────────────────────────────────────────

def _from_finnhub(tickers: list) -> dict:
    """
    [修复版] 从 Finnhub 获取实时报价、当日成交量及历史均量。
    """
    import finnhub

    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        logger.error("FINNHUB_API_KEY 未设置！")
        return {sym: None for sym, _ in tickers}

    client  = finnhub.Client(api_key=api_key)
    results = {}

    for sym, name in tickers:
        try:
            # 1. 获取实时报价与当日成交量 (v 字段)
            res = client.quote(sym)
            if not res or res.get("c") in (0, None):
                results[sym] = None
                continue

            close_today = res["c"]
            close_prev  = res["pc"]
            current_vol = res.get("v", 0)  # 获取当日成交量
            change_pct  = (close_today - close_prev) / close_prev * 100 if close_prev else 0.0

            # 2. 获取财务数据以提取“10日平均成交量” (用于计算量比)
            avg_vol = 0
            try:
                # 针对指数（如 SPY/QQQ）和个股通用的指标接口
                financials = client.company_basic_financials(sym, 'all')
                avg_vol = financials.get('metric', {}).get('10DayAverageTradingVolume', 0)
            except Exception as fe:
                logger.debug("无法获取 %s 的均量指标: %s", sym, fe)

            results[sym] = {
                "name":       name,
                "price":      close_today,
                "change_pct": change_pct,
                "volume":     current_vol,
                "avg_volume": avg_vol,
                "note":       ""
            }
            # Finnhub 免费版限速保护 (每次请求后 sleep)
            time.sleep(1.2)
        except Exception as e:
            logger.warning("Finnhub: %s 请求失败：%s", sym, e)
            results[sym] = None

    return results
