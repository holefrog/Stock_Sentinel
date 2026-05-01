# agent/discord_utils.py
# v8.2 - 统一使用显式相对导入

import os
import sys
import subprocess
import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timezone
import discord
from .config import settings, load
import requests
import json

logger = logging.getLogger(__name__)

# 基础常量获取
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

_cfg = load()
DISCORD_API_BASE = _cfg["discord"]["api_base_url"]
USER_AGENT = _cfg["discord"]["user_agent"]

MAX_LENGTH = 1900


def _get_rest_headers():
    """构造统一的 REST 请求头"""
    return {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT
    }


def get_status_color(change_val: float) -> int:
    if change_val > 0: return 0x57F287
    elif change_val < 0: return 0xED4245
    else: return 0x95A5A6

def create_embed(title: str = "", description: str = "", color_val: float = 0.0, url: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=get_status_color(color_val),
        timestamp=datetime.now(timezone.utc),
        url=url or None  # Discord 要求 url 不能是空字符串
    )
    embed.set_footer(text="StockSentinel Project • Market Data")
    return embed

async def send_to_channel(channel_id: int, text: str):
    """使用 REST API 发送纯文本消息"""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = _get_rest_headers()
    
    for chunk in _split(text):
        payload = {"content": chunk}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"REST 发送文本失败: {e}")

async def send_embeds(channel_id: int, embeds: List[discord.Embed]):
    """使用 REST API 发送 Embeds"""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = _get_rest_headers()
    
    # 转换为 Discord API 接受的字典格式
    raw_embeds = [e.to_dict() for e in embeds]
    
    # Discord 限制单次发送最多 10 个 Embed
    for i in range(0, len(raw_embeds), 10):
        payload = {"embeds": raw_embeds[i:i+10]}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"REST 发送 Embed 失败: {e}")

def _split(text: str):
    if len(text) <= MAX_LENGTH: return [text]
    chunks = []
    while text:
        if len(text) <= MAX_LENGTH:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, MAX_LENGTH)
        if split_at == -1: split_at = MAX_LENGTH
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    return chunks

def save_markdown(content_dir: str, filename: str, front_matter: str, body: str) -> str:
    os.makedirs(content_dir, exist_ok=True)
    filepath = os.path.join(content_dir, filename)
    full_content = f"""---
{front_matter}
---

{body}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
    logger.info("Markdown 已保存：%s", filepath)
    return filepath

def run_hugo(cfg: dict) -> bool:
    """
    执行 Hugo 构建并全量同步到 Nginx 根目录。
    直接通过 settings 单例获取 12-Factor 环境注入的绝对物理路径。
    """
    hugo_working_dir = str(settings.HUGO_ROOT)
    public_dir       = str(settings.HUGO_ROOT / "public")
    web_root         = str(settings.WEB_ROOT)
    
    domain      = os.environ.get("SENTINEL_DOMAIN", "localhost")
    prefix      = os.environ.get("SENTINEL_PREFIX", "sentinel")
    
    base_url    = f"https://{domain}/{prefix}/"
    
    hugo_exe    = settings.HUGO_EXE

    hugo_cmd = [
        hugo_exe, "--gc", "--minify", "--buildFuture", 
        "--destination", public_dir, 
        "--baseURL", base_url
    ]
        
    logger.info("执行 Hugo 构建 (工作目录: %s)：%s", hugo_working_dir, " ".join(hugo_cmd))
    
    result = subprocess.run(hugo_cmd, cwd=hugo_working_dir, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error("Hugo 构建失败：\n%s", result.stderr)
        return False
    else:
        summary = "\n".join([line for line in result.stdout.split("\n") if "Total in" in line or "Pages" in line])
        logger.info("✅ Hugo 构建成功！\n%s", summary)
    
    os.makedirs(web_root, exist_ok=True)

    source_path = public_dir + "/"
    target_path = web_root + "/"
    
    rsync_cmd = ["rsync", "-av", "--delete", source_path, target_path]
    logger.info("执行全站同步：%s", " ".join(rsync_cmd))
    result2 = subprocess.run(rsync_cmd, capture_output=True, text=True)
    
    if result2.returncode != 0:
        logger.error("Rsync 同步失败：\n%s", result2.stderr)
        return False
    else:
        logger.info("✅ 全站同步成功！门户、新闻与报告已全部上线。")
        
    return True
    
    
async def send_error(channel_id: int, task: str, step: str, reason: str):
    reason_short = str(reason)[:200]
    text = f"⚠️ **{task}失败** | 步骤：{step}\n```{reason_short}```"
    try: await send_to_channel(channel_id, text)
    except Exception as e: logger.error("send_error 失败：%s", e)

async def publish_report(channel_id: int, task_name: str, embeds: list, 
                         filename: str, front_matter: str, body: str, cfg: dict) -> bool:
    """
    统一的报告发布流水线：发送 Embed -> 保存 Markdown -> 触发 Hugo 构建。
    """
    try:
        if embeds:
            await send_embeds(channel_id, embeds)
            logger.info("%s Embed 已发送", task_name)
    except Exception as e:
        logger.error("Discord 发送失败：%s", e)
        await send_error(channel_id, task_name, "Discord 发送", str(e))
        return False

    try:
        save_markdown(str(settings.REPORTS_DIR), filename, front_matter, body)
    except Exception as e:
        logger.error("Markdown 保存失败：%s", e)
        await send_error(channel_id, task_name, "Markdown 保存", str(e))
        return False

    try:
        if not run_hugo(cfg):
            await send_error(channel_id, task_name, "Hugo 构建", "返回非零退出码，请查看日志")
            return False
    except Exception as e:
        logger.error("Hugo 流程异常：%s", e)
        await send_error(channel_id, task_name, "Hugo 构建", str(e))
        return False

    return True
