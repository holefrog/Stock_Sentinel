# agent/brief.py
import os
import requests
import logging
import time

try:
    from curl_cffi import requests as cffi_requests
    import trafilatura
    HAS_LOCAL_SCRAPER = True
except ImportError:
    HAS_LOCAL_SCRAPER = False

logger = logging.getLogger(__name__)

def fetch_content(url: str, timeout: int = 20) -> str:
    """
    抓取网页正文，采用三级降级策略绕过反爬：
    1. 优先：本地伪装 Chrome 指纹直连抓取 + Trafilatura 提取正文（绕过 Cloudflare/Datadome）
    2. 降级：Jina.ai 免费提取接口
    3. 兜底：Jina.ai API Key 提取接口（解决 429 限流问题）
    """
    if not url:
        return ""

    # -------------------------------------------------------------
    # 第一级：本地 curl_cffi 伪装指纹 + trafilatura 提取
    # -------------------------------------------------------------
    if HAS_LOCAL_SCRAPER:
        try:
            logger.info(f"尝试本地高匿伪装抓取: {url}")
            # 使用 chrome110 指纹绕过多数 TLS 拦截
            resp = cffi_requests.get(url, impersonate="chrome110", timeout=timeout)
            resp.raise_for_status()
            
            # 使用 trafilatura 智能提取正文（去除广告/导航栏）
            # include_comments=False 避免抓到无关评论
            text = trafilatura.extract(resp.text, include_comments=False)
            
            if text and len(text.strip()) > 100:
                logger.info("✅ 本地抓取并提取成功！")
                return text.strip()
            else:
                logger.warning("⚠️ 本地提取到的正文过短或为空，降级至 Jina")
        except Exception as e:
            logger.warning(f"⚠️ 本地抓取异常: {e}，降级至 Jina")
    else:
        logger.warning("未安装 curl_cffi 或 trafilatura，直接使用 Jina。建议安装以增强反爬能力。")

    # -------------------------------------------------------------
    # 第二级：Jina.ai 免费模式
    # -------------------------------------------------------------
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "X-Return-Format": "markdown",
        "User-Agent": "Mozilla/5.0 StockSentinel/1.0"
    }
    
    api_key = os.environ.get("JINA_API_KEY", "").strip()

    try:
        time.sleep(1) # 基础限速保护
        logger.info(f"正在通过 Jina 抓取 (免费模式): {url}")
        resp = requests.get(jina_url, headers=headers, timeout=timeout)

        # -------------------------------------------------------------
        # 第三级：Jina.ai API Key 模式 (应对 429)
        # -------------------------------------------------------------
        if resp.status_code == 429 and api_key:
            logger.warning(f"⚠️ Jina 免费接口触发限速 (429)，切换至 API Key 模式重试: {url}")
            headers["Authorization"] = f"Bearer {api_key}"
            time.sleep(1)
            resp = requests.get(jina_url, headers=headers, timeout=timeout)

        resp.raise_for_status()
        return resp.text.strip()

    except requests.exceptions.RequestException as e:
        logger.warning(f"❌ 正文最终抓取失败: {url}, 错误: {e}")
        return ""
