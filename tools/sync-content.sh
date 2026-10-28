#!/usr/bin/env bash
# 把 MSP 主仓库的 docs/wiki 同步到本站的 content/，然后重新生成文档页。
#
#   MSP_REPO=../MSP ./tools/sync-content.sh
#
# 主仓库的 docs/wiki 是唯一真源；content/ 是给「站点零依赖、离线可构建」用的镜像。
set -euo pipefail
MSP_REPO="${MSP_REPO:?请指定 MSP 主仓库路径，例如 MSP_REPO=../MSP}"
cp -f "$MSP_REPO"/docs/wiki/*.md content/
python tools/build.py
