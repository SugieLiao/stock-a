#!/bin/bash
# stock-a 重新抽数哨兵：由 launchd 每分钟调用一次。
# 流程：GET /api/queue 取 pending 命令 → 无则静默退出 → 有则 flock 互斥跑 daily_pipeline.py
#       → 互斥撞车则命令保留下轮重试 → 否则 POST /api/queue/done 并邮件通知。
# 任何读取失败都静默退出（绝不发失败邮件）。
set -uo pipefail

BASE="/Users/sugieliao/WorkBuddy/A股每日复盘"
QUEUE_URL="https://liaohao.cc/api/queue"
DONE_URL="https://liaohao.cc/api/queue/done"
PY="/usr/bin/python3"
LOG="$BASE/logs/watch_reextract.log"
LOCK="$BASE/.watch_reextract.lock"
mkdir -p "$BASE/logs"

log(){ echo "$(date '+%F %T') $*" >> "$LOG"; }

# 1) 读队列（10s 超时；失败静默）
RAW=$(curl -s --max-time 10 "$QUEUE_URL" 2>/dev/null)
if [ -z "$RAW" ]; then exit 0; fi

# 取第一个 pending 的 reextract 命令 → "id|date"
CMDS=$(printf '%s' "$RAW" | "$PY" -c "
import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
for c in d.get('commands', []):
    if c.get('status')=='pending' and c.get('cmd')=='reextract':
        print(c.get('id','')+'|'+(c.get('date') or ''))
        sys.exit(0)
print('')
")
[ -z "$CMDS" ] && exit 0   # 无指令 → 静默

CID="${CMDS%%|*}"
CDATE="${CMDS#*|}"

# 2) 哨兵自身 flock 互斥（防并发唤醒）
exec 9>"$LOCK"
flock -n 9 || { log "哨兵互斥锁被占用，跳过本轮"; exit 0; }

log "发现 reextract 命令 id=$CID date=${CDATE:-<auto>}，开始执行 daily_pipeline"
if [ -n "$CDATE" ]; then
  OUT=$(cd "$BASE" && "$PY" daily_pipeline.py "$CDATE" 2>&1); RC=$?
else
  OUT=$(cd "$BASE" && "$PY" daily_pipeline.py 2>&1); RC=$?
fi

# 3) 互斥撞车：与午间/收盘版并发 → 命令保留，下轮重试
if printf '%s' "$OUT" | grep -q "检测到另一个 daily_pipeline"; then
  log "检测到另一流水线实例在跑，命令 id=$CID 保留，下轮重试"
  exit 0
fi

echo "$OUT" >> "$LOG"
log "daily_pipeline 退出码=$RC，命令 id=$CID 标记 done"
curl -s --max-time 10 -X POST "$DONE_URL?id=$CID" > /dev/null 2>&1

if [ "$RC" -eq 0 ]; then
  bash "$BASE/send_notify.sh" "stock-a 重新抽数完成" "报告已重新生成并发布到 liaohao.cc/stock-a" >> "$LOG" 2>&1 || true
else
  log "执行失败（rc=$RC），见上方日志"
fi
exit 0
