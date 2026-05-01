# agent/report.py
# v8.1 - 晚报增强版：支持从数据库提取具体时间并展示
import argparse
import asyncio
import logging
import os
import sys
import json
import sqlite3
from datetime import datetime

from . import config
from .config import settings  # 引入全局单例配置对象
from . import data_engine
from . import discord_utils
from . import news_dedup
from . import news_engine
from . import translator
from . import llm_gateway
from . import brief
from . import renderer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("report")

async def distribute_news(cfg: dict, news_items: list):
    """
    [完整保留] 按照 news.toml 的配置，将新闻分发到不同的 Discord 频道。
    已适配新的 content_zh (中文深度解析) 显示。
    """
    source_map = {}
    for s in cfg["news"]["sources"]:
        if s.get("enabled"):
            ch_key = s.get("channel", s.get("channel_id"))
            actual_ch_id = config.resolve_channel(cfg, ch_key) if ch_key else "0"
            source_map[s["name"]] = {
                "channel": int(actual_ch_id) if str(actual_ch_id).isdigit() else None,
                "min_score": s.get("min_score", 0)
            }

    channel_batches = {}
    for item in news_items:
        src_info = source_map.get(item["source"]) or source_map.get(item["source"].split('/')[0])
        if not src_info or not src_info["channel"]: continue
        if item.get("ai_score", 0) < src_info["min_score"]: continue
        
        ch_id = src_info["channel"]
        if ch_id not in channel_batches: channel_batches[ch_id] = []
        
        tickers = " ".join(f"`{t}`" for t in item["tickers"][:3]) if item.get("tickers") else ""
        
        # 修复：格式化分数为两位数，并移除“分”字
        score_val = f"{int(item['ai_score']):02d}"
        ai_badge = f"**[{'🔥' if item['ai_score']>=8 else '🤖'} {item.get('ai_engine', 'AI')} {score_val}]** "
        title_display = f"[{item.get('title_zh', item['title'])}]({item['url']})"
        
        
        # 【微调】增加时间戳显示
        time_tag = f" `[{item.get('published', '')}]`" if item.get('published') else ""
        msg = f"**{item['source']}** {tickers}{time_tag}\n📰 {ai_badge}{title_display}"
        
        # 优先显示深度中文解析，没有则显示摘要
        if item.get("content_zh"):
            msg += f"\n\n🔍 **AI 中文深度解析**:\n{item['content_zh']}"
        elif item.get("summary"):
            msg += f"\n> {item['summary'][:150]}..."
            
        channel_batches[ch_id].append(msg)

    for ch_id, msgs in channel_batches.items():
        full_msg = f"🚨 **报告分发预警** | {len(msgs)} 条重要资讯\n\n" + "\n\n".join(msgs)
        chunks = discord_utils._split(full_msg)
        for chunk in chunks:
            await discord_utils.send_to_channel(ch_id, chunk)

async def main(channel_id: int, report_type: str):
    cfg = config.load()
    task_name = "早报" if report_type == "morning" else "晚报"
    
    # 完美解耦：直接从 settings 获取绝对路径并转为字符串供 SQLite 使用
    db_path = str(settings.DB_PATH)

    # 1. 获取基础配置与交易日状态
    market_context, watch_list = config.get_targets(cfg)
    mkt = data_engine.market_status()
    
    # [新增] 休市 Discord 提示
    if not mkt.get("is_trading_day", True):
        logger.warning(f"🕒 当前非交易日，取消{task_name}生成。")
        try:
            msg = f"🛏️ **休市提示** | 当前时间为非交易日（或美股休市），今日无{task_name}生成。好好休息！"
            await discord_utils.send_to_channel(channel_id, msg)
        except Exception as e:
            logger.error(f"发送休市提示失败: {e}")
        return

    calendar, news_items, ai_summary = {}, [], None

    # 2. 早报逻辑 (完整保留 fetch_calendar)
    if report_type == "morning":
        calendar = news_engine.fetch_calendar(cfg)
        
    # 3. 晚报逻辑 (全新架构：直接从数据库抓取当日盘点)
    else:
        news_dedup.init_db(db_path)
        
        rpt_cfg = cfg["report"]
        min_score = rpt_cfg["min_score_threshold"]
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # [核心升级] 晚报不再重复请求网络与 AI 打分，直接从数据库提取今日高分预警
        try:
            with sqlite3.connect(db_path) as conn:
                # 【修改点】SQL 增加 r.created_at
                cursor = conn.execute("""
                    SELECT r.guid, r.url, r.score, r.title, r.title_zh, r.reason,
                           b.translated_content, b.full_content, r.created_at, r.ai_engine
                    FROM news_registry r
                    LEFT JOIN news_briefs b ON r.guid = b.guid
                    WHERE r.created_at LIKE ? AND r.score >= ?
                    ORDER BY r.score DESC LIMIT 15
                """, (f"{today_str}%", min_score))
                
                rows = cursor.fetchall()
                for row in rows:
                    guid,url,score,title, title_zh,reason,trans_content,full_content,created_at,ai_engine = row                    
                    # 【新增】转换 ISO 时间为 HH:MM ET 格式
                    try:
                        # created_at 格式为 2026-04-25T22:00:14.xxx
                        dt_obj = datetime.fromisoformat(created_at)
                        pub_time_str = dt_obj.strftime(" %H:%M ET")
                    except:
                        pub_time_str = ""

                    news_items.append({
                        "guid": guid,
                        "url": url,
                        "ai_score": score,
                        "title": title or "",
                        "title_zh": title_zh or title or "",
                        "reason": reason or "",
                        "content_zh": trans_content or "",
                        "full_content": full_content or "",
                        "source": "今日焦点", 
                        "published": pub_time_str,
                        "tickers": [],
                        "ai_engine": ai_engine or "AI" 
                    })
            logger.info(f"晚报：从数据库盘点到 {len(news_items)} 条今日重要预警（包含时间戳）。")
        except Exception as e:
            logger.error(f"提取今日新闻数据失败: {e}")

        # E. 生成晚报 AI 深度总结 (基于本地已提纯的数据，极大节省 Token)
        if news_items:
            sys_prompt = rpt_cfg["summary_prompt"]["system"]
            payload_data = []
            for n in news_items:
                raw_content = n.get("full_content", "")
                payload_data.append({
                    "title": n["title_zh"] or n["title"], 
                    "content": raw_content[:2500] if raw_content else n.get("content_zh", "")[:500]
                })
            user_payload = json.dumps(payload_data, ensure_ascii=False)
            ai_summary, _ = llm_gateway.query(sys_prompt, user_payload, db_path)

    # 4. 获取最终行情
    mc_data = data_engine.fetch(market_context)
    watch_data = data_engine.fetch(watch_list)

    # 5. 渲染视觉组件 (调用工厂)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M ET")
    date_str = datetime.now().strftime("%Y-%m-%d")
    DOMAIN = os.getenv("SENTINEL_DOMAIN", "")
    APP_PREFIX = os.getenv("SENTINEL_PREFIX", "sentinel")
    report_url = f"https://{DOMAIN}/{APP_PREFIX}/reports/" if DOMAIN else ""

    embeds = renderer.build_report_embeds(
        report_type, market_context, watch_list, mc_data, watch_data,
        now_str, mkt["note"], calendar, news_items, ai_summary,
        report_url=report_url  # 直接传进去
    )

    front, body, fname = renderer.build_report_markdown(
        report_type, market_context, watch_list, mc_data, watch_data, 
        now_str, date_str, mkt["note"], calendar, news_items, ai_summary
    )

    # 6. 发布
    await discord_utils.publish_report(channel_id, task_name, embeds, fname, front, body, cfg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--type", type=str, required=True, choices=["morning", "evening"])
    args = parser.parse_args()
    asyncio.run(main(args.channel, args.type))
