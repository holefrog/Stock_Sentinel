# agent/translator.py
# v2.1 - 修复绝对路径导入
import os
import logging
import requests
from . import llm_gateway

logger = logging.getLogger(__name__)

def translate_title(text: str, cfg: dict) -> str:
    """调用 DeepL API 翻译标题。失败或无 Key 时降级调用 LLM 翻译。"""
    if not text:
        return ""
    
    api_key = os.environ.get("DEEPL_API_KEY", "").strip()
    
    if api_key:
        # 默认使用免费接口
        url = cfg["services"]["translator"]["url_free"]
        # 根据后缀智能判断：如果不带 :fx 后缀，通常是 Pro 版付费 API
        if not api_key.endswith(":fx"):
            url = cfg["services"]["translator"]["url_pro"]
            
        headers = {
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "text": [text],
            "target_lang": "ZH"
        }
        
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=5)
            resp.raise_for_status()
            res_json = resp.json()
            translations = res_json.get("translations", [])
            if translations:
                return translations[0].get("text", "")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 456:
                logger.warning("⚠️ DeepL 免费额度已用尽 (456)，降级使用 LLM 翻译标题...")
            else:
                logger.warning("⚠️ DeepL 翻译失败: %s，降级使用 LLM 翻译标题...", e)
        except Exception as e:
            # 失败时不退出，记录日志，继续下面的 LLM 兜底
            logger.warning("⚠️ DeepL 翻译异常: %s，降级使用 LLM 翻译标题...", e)
    else:
        logger.debug("未找到 DeepL API Key，直接使用 LLM 翻译标题")

    # --- 降级到 LLM 翻译逻辑 ---
    from .config import settings
    db_path = str(settings.DB_PATH)
    sys_prompt = cfg["news"]["title_translation_prompt"]["system"]
    
    try:
        forced_engine = cfg["news"]["preferred_engine"]
        translated_text, _ = llm_gateway.query(sys_prompt, text[:500], db_path, forced_engine=forced_engine)
        return translated_text.strip().strip('"').strip("'")
    except Exception as e:
        logger.error(f"❌ LLM 标题兜底翻译失败: {e}")
        return "暂无法翻译标题"
    
    
def translate_full_report(content: str, cfg: dict) -> str:
    """使用 LLM 对抓取的正文进行中文深度翻译与要点总结"""
    if not content:
        return ""
    
    # 使用单例 AppConfig 获取数据库路径
    from .config import settings
    db_path = str(settings.DB_PATH)
    
    # 从统一配置加载 AI Prompt (此时 config.py 已确保其存在)
    sys_prompt = cfg["news"]["full_translation_prompt"]["system"]
    
    # 限制输入长度，防止 Token 溢出，取精华部分
    max_len = cfg["news"]["max_summary_input_len"]
    payload = content[:max_len] 
    
    try:
        # 强制使用 AI 引擎进行翻译
        forced_engine = cfg["news"]["preferred_engine"]
        translated_text, _ = llm_gateway.query(sys_prompt, payload, db_path, forced_engine=forced_engine)
        return translated_text
    except Exception as e:
        logger.error(f"全文翻译失败: {e}") 
        return ""
