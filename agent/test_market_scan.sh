#!/bin/bash
# market_test.sh - Stock-Sentinel 市场异动扫描测试脚本

APP_DIR="/root/stock-sentinel"
VENV_PYTHON="$APP_DIR/venv/bin/python"

# 1. 环境准备与变量加载
if [ -f "$APP_DIR/.env" ]; then
    set -a
    source "$APP_DIR/.env"
    set +a
    echo "✅ 环境变量已加载"
else
    echo "❌ 错误: 找不到 .env 配置文件"
    exit 1
fi

# 2. 确定测试频道
# 优先使用 .env 中的扫描频道 ID，若无则使用默认 ID
SCAN_CH=${SENTINEL_SCAN_CH:-1495609759439655023}

echo "🚀 开始市场异动扫描测试..."
echo "📡 目标频道: $SCAN_CH"

# 3. 执行扫描脚本
# 建议先执行一次，观察是否因为“市场未开盘”而跳过
export PYTHONPATH=$APP_DIR
$VENV_PYTHON -m agent.market_scan --channel $SCAN_CH --force

# 4. 结果指引
echo "--------------------------------------"
echo "✨ 测试指令发送完毕。"
echo "💡 提示: "
echo "1. 如果日志显示 '市场未开盘'，请修改 agent/market_scan.py 临时跳过开启状态检查。"
echo "2. 如果没有 Discord 输出，说明当前市场波动未达到配置的阈值。"
echo "3. 检查 logs/scan.log 查看详细抓取耗时（由于增加了均量抓取，耗时会略微增加）。"
