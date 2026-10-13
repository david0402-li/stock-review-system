#!/bin/bash
# 本地一键部署
cd "$(dirname "$0")"
echo "═══ 本地构建 ═══"
python3 scripts/build_static.py
echo ""
echo "═══ 推送到 GitHub（触发自动部署）═══"
git add -A
git commit -m "deploy: $(date +%Y-%m-%d\ %H:%M)"
git push
echo ""
echo "✅ 推送完成，GitHub Actions 将自动部署到 Cloudflare"
