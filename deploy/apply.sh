#!/bin/bash
set -euo pipefail

# ── 1. 配置区域 ──────────────────────────────────────────
INV="inventory.yml"
PB="site.yml"
# 如果你的 vars.yml 里定义了私钥路径，可以在这里手动指定进行预检
# KEY="keys/vps_primary_key" 

echo "--------------------------------------------------------"
echo "🚀 StockSentinel - Ansible 自动化部署系统"
echo "--------------------------------------------------------"

# ── 2. 环境预检 ──────────────────────────────────────────

# 检查并安装 Ansible
if ! command -v ansible-playbook &>/dev/null; then
    echo "📦 正在安装 Ansible..."
    sudo apt-get update -qq && sudo apt-get install -y ansible
fi

# 检查 ansible-lint 是否安装 (可选，如果不存在则跳过第一步)
HAS_LINT=false
if command -v ansible-lint &>/dev/null; then
    HAS_LINT=true
fi

# ── 3. 执行三阶段校验 ──────────────────────────────────────

# [阶段 1/3] 静态分析
if [ "$HAS_LINT" = true ]; then
    echo ">>> [1/3] 正在执行 ansible-lint 静态分析..."
    if ! ansible-lint "$PB"; then
        echo "❌ Lint 检查未通过，请修复上述格式或规范问题。"
        exit 1
    fi
else
    echo ">>> [1/3] 跳过 Lint 检查 (未安装 ansible-lint)"
fi

# [阶段 2/3] 语法校验
echo ">>> [2/3] 正在执行 Ansible 语法校验..."
if ! ansible-playbook -i "$INV" "$PB" --syntax-check >/dev/null; then
    echo "❌ 语法错误：请检查 YAML 缩进或模块参数。"
    exit 1
fi
echo "✅ 语法正常"

# [阶段 3/3] 连接测试
echo ">>> [3/3] 正在探测目标主机连通性..."
if ! ansible all -i "$INV" -m ping >/dev/null; then
    echo "❌ 无法连接到服务器！请检查网络、IP 或 SSH 密钥配置。"
    exit 1
fi
echo "✅ 连接成功"

# ── 4. 正式执行部署 ──────────────────────────────────────
echo "--------------------------------------------------------"
echo "🛠️  正在开始最终部署任务..."
echo "--------------------------------------------------------"

# 自动判断是否需要 sudo 密码 (根据 sudo -n 的状态)
if sudo -n true 2>/dev/null; then
    ansible-playbook -i "$INV" "$PB" "$@"
else
    # 如果 site.yml 需要 Vault 密码，用户可以通过命令行参数 $@ 传入 --ask-vault-pass
    ansible-playbook -i "$INV" "$PB" --ask-become-pass "$@"
fi

echo -e "\n🎉 部署任务执行完毕！"
