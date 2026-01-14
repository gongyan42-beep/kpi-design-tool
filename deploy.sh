#!/bin/bash
# KPI 设计工具部署脚本
# 重要：不要覆盖服务器上的 data 目录！

set -e

echo "📦 打包项目（排除 data 目录）..."
tar -czf /tmp/kpi-deploy.tar.gz \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='.DS_Store' \
    --exclude='data' \
    .

echo "📤 上传到服务器..."
scp -i ~/.ssh/baota_server_key /tmp/kpi-deploy.tar.gz root@118.25.13.91:/www/wwwroot/

echo "🔧 在服务器上部署..."
ssh -i ~/.ssh/baota_server_key root@118.25.13.91 "
    cd /www/wwwroot

    # 创建临时目录
    rm -rf kpi-design-tool-new
    mkdir kpi-design-tool-new

    # 解压代码
    tar -xzf kpi-deploy.tar.gz -C kpi-design-tool-new

    # 保留现有的 data 目录（重要！防止嵌套！）
    mkdir -p kpi-design-tool-new/data
    if [ -d kpi-design-tool/data ]; then
        echo '✅ 保留现有数据目录'
        # 复制内容而非目录本身，避免产生 data/data 嵌套
        cp -r kpi-design-tool/data/* kpi-design-tool-new/data/ 2>/dev/null || true
        # 清理可能存在的嵌套目录
        rm -rf kpi-design-tool-new/data/data 2>/dev/null || true
    else
        echo '⚠️ 无现有数据目录'
    fi

    # 备份旧版本
    rm -rf kpi-design-tool-backup
    mv kpi-design-tool kpi-design-tool-backup 2>/dev/null || true

    # 启用新版本
    mv kpi-design-tool-new kpi-design-tool

    # 重建 Docker
    cd kpi-design-tool
    docker-compose down
    docker-compose up -d --build

    # 清理 Nginx 缓存
    rm -rf /www/server/nginx/proxy_cache_dir/*
    nginx -s reload

    echo '✅ 部署完成！'
"

echo ""
echo "🎉 部署成功！访问 https://kpi.longgonghuohuo.com"
