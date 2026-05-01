#!/bin/bash
# news_test.sh v8.7

APP_DIR="/root/stock-sentinel"
DB_PATH="$APP_DIR/data/sentinel.db"

# 1. 加载并验证环境
if [ -f "$APP_DIR/.env" ]; then
    set -a; source "$APP_DIR/.env"; set +a
    echo "✅ 环境加载完成 (Key 长度: ${#FINNHUB_API_KEY})"
else
    echo "❌ 错误: 找不到 .env 文件"
    exit 1
fi

# 1.5 强制清理数据库最后一条记录，确保扫描器不会因为去重而跳过测试
if [ -f "$DB_PATH" ]; then
    echo "🧹 正在清理数据库最新 10 条记录以绕过去重逻辑..."
    # 同时清理登记表和正文表
    # 【修复点】将 guid = (SELECT ...) 改为 guid IN (SELECT ...)
    sqlite3 "$DB_PATH" "DELETE FROM news_registry WHERE guid IN (SELECT guid FROM news_registry ORDER BY created_at DESC LIMIT 10);"
    sqlite3 "$DB_PATH" "DELETE FROM news_briefs WHERE guid NOT IN (SELECT guid FROM news_registry);"
    echo "✅ 清理完成。"
else
    echo "ℹ️ 数据库尚未建立，跳过清理步奏。"
fi

# 2. 执行扫描 (注意观察日志中的分数)
echo "📡 正在执行新闻扫描..."
export PYTHONPATH=$APP_DIR
$APP_DIR/venv/bin/python -m agent.news_scanner --channel 1495609759439655023

# 3. 无论是否有新新闻，都强制执行一次 Hugo 编译以验证路径
echo "🏗️ 正在构建静态页面到 Nginx 目录..."
cd $APP_DIR/hugo
${HUGO_PATH:-/usr/local/bin/hugo} --gc --cleanDestinationDir \
    -b "https://${SENTINEL_DOMAIN}/sentinel/" \
    --destination "/usr/share/nginx/${SENTINEL_DOMAIN}/sentinel"

# 4. 修正权限
chown -R nginx:nginx /usr/share/nginx/${SENTINEL_DOMAIN}/sentinel
chmod -R 755 /usr/share/nginx/${SENTINEL_DOMAIN}/sentinel

echo "📂 Nginx 目录新闻列表 (前 5 个):"
ls -lt /usr/share/nginx/${SENTINEL_DOMAIN}/sentinel/news/ | head -n 5
