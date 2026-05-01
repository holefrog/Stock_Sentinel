# agent/market_scan.py
# v5.3 - 统一使用显式相对导入

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from . import config
from . import data_engine
from . import discord_utils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("market_scan")


# ── 异动检测 ───────────────────────────────────────────────────────────────────

def detect_anomalies(data: dict, alert_pct: float, spike_x: float) -> list:
    """
    [修复版] 检测价格和成交量异动。
    由原来的 elif 改为独立判断，确保异动信息不遗漏。
    """
    alerts = []
    for sym, d in data.items():
        if d is None:
            continue

        item_alerts = []
        # 1. 价格异动判断
        if abs(d["change_pct"]) >= alert_pct:
            direction = "📈" if d["change_pct"] > 0 else "📉"
            item_alerts.append(f"{direction} 价格 {d['change_pct']:+.2f}%")

        # 2. 成交量异动判断 (必须有均量数据且满足倍率)
        if (d.get("avg_volume") and d["avg_volume"] > 0):
            ratio = d["volume"] / d["avg_volume"]
            if ratio >= spike_x:
                item_alerts.append(f"📊 放量 {ratio:.1f}x")

        # 如果有任何一项触发，组合成单条通知
        if item_alerts:
            alert_str = " | ".join(item_alerts)
            alerts.append(
                f"**{d['name']} ({sym})** {d['price']:.2f} ({alert_str})"
            )

    return alerts


# ── 主流程 ─────────────────────────────────────────────────────────────────────

async def main(channel_id: int, force: bool = False):
    cfg         = config.load()
    
    # 获取扫描配置参数
    alert_pct   = cfg["market"]["alert_threshold_pct"]
    spike_x     = cfg["market"]["volume_spike_threshold"]

    # 合并监控名单
    watch_list   = [(i["ticker"], i["name"]) for i in cfg["market"].get("watch_list", [])]
    indices_list = [(i["ticker"], i["name"]) for i in cfg["market"].get("indices", [])]
    scan_targets = watch_list + indices_list

    # 0. 市场状态检查
    if not force:
        mkt = data_engine.market_status()
        if not mkt["is_open"]:
            logger.info("市场未开盘，跳过扫描 (%s)", mkt.get("note", "休市"))
            return

    if not scan_targets:
        logger.info("监控标的为空，跳过扫描")
        return

    # 1. 抓取数据
    logger.info("开始市场异动扫描...")
    try:
        market_data = data_engine.fetch(scan_targets)
    except Exception as e:
        logger.error("扫描数据抓取失败：%s", e)
        return

    # 2. 检测异动
    alerts = detect_anomalies(market_data, alert_pct, spike_x)

    if not alerts:
        logger.info("扫描完成，无显著异动")
        return

    # 3. 发送 Discord 通知
    now_str = datetime.now().strftime("%H:%M ET")
    lines   = [f"🔍 **实时市场异动监控** | {now_str}", ""] + alerts
    msg     = "\n".join(lines)

    try:
        await discord_utils.send_to_channel(channel_id, msg)
        logger.info("异动通知已成功发送")
    except Exception as e:
        logger.error("Discord 发送失败：%s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--force", action="store_true", help="Bypass market open check")
    args = parser.parse_args()
    asyncio.run(main(args.channel, args.force))
