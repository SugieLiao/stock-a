#!/usr/bin/env bash
# 发送 A股 复盘完成通知邮件
# 发件人：agently-cli 登录账号的主别名（liaohao@agent.qq.com）
# 收件人：hao.liao01@qq.com（外部 QQ 邮箱，可手机/电脑收信）
# 用法：bash send_notify.sh "<标题>" "<正文，可含换行>"
set -euo pipefail

BIN="/Users/sugieliao/.workbuddy/binaries/node/versions/22.22.2/bin/agently-cli"
TO="hao.liao01@qq.com"

SUBJECT="${1:-A股复盘通知}"
BODY="${2:-}"

if [ -z "$BODY" ]; then
  echo "用法: bash send_notify.sh \"<标题>\" \"<正文>\"" >&2
  exit 1
fi

"$BIN" message +send --to "$TO" --subject "$SUBJECT" --body "$BODY" --confirmed
