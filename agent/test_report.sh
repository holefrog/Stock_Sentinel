#!/bin/bash
# report_test.sh v1.0

APP_DIR="/root/stock-sentinel"
TEST_CHANNEL="1490212708795023470"

# 1. 加载并验证环境
if [ -f "$APP_DIR/.env" ]; then
    set -a; source "$APP_DIR/.env"; set +a
    echo "✅ 环境加载完成 (Key 长度: ${#FINNHUB_API_KEY})"
else
    echo "❌ 错误: 找不到 .env 文件"
    exit 1
fi

# 2. 执行报告生成 (默认测试晚报 evening，因为它依赖本地数据库)
echo "🌆 正在执行收盘晚报生成测试..."
export PYTHONPATH=$APP_DIR
$APP_DIR/venv/bin/python -m agent.report --type evening --channel $TEST_CHANNEL

# 3. 强制执行 Hugo 编译以验证全站同步逻辑
echo "🏗️ 正在构建静态页面并同步至 Nginx 目录..."
cd $APP_DIR/hugo
${HUGO_PATH:-/usr/local/bin/hugo} --gc --cleanDestinationDir \
    -b "https://${SENTINEL_DOMAIN}/sentinel/" \
    --destination "/usr/share/nginx/${SENTINEL_DOMAIN}/sentinel"

# 4. 修正权限
chown -R nginx:nginx /usr/share/nginx/${SENTINEL_DOMAIN}/sentinel
chmod -R 755 /usr/share/nginx/${SENTINEL_DOMAIN}/sentinel

echo "📂 Nginx 目录报告列表 (最新 5 个):"
ls -lt /usr/share/nginx/${SENTINEL_DOMAIN}/sentinel/reports/ | head -n 5

echo "--------------------------------------"
echo "✨ 测试建议："
echo "1. 检查 Discord 频道是否收到带图表的 Embed 消息。"
echo "2. 访问 https://${SENTINEL_DOMAIN}/sentinel/reports/ 查看网页版是否更新。"
echo "3. 如果晚报内容为空，请确认今日是否有评分 >= 7 的新闻入库。"
