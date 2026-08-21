#!/usr/bin/env python3
# 取通达信扩展数据 38/39/40 号（TR情绪监测：HTR10/HTR20/HTR40），写 data/tr_emotion.json。
# 来源：通达信本地扩展数据文件 C:\\new_tdx64\\T0002\\extdata\\extdata_{38,39,40}.dat
# 二进制格式：每条记录 12 字节 = 日期(uint32 YYYYMMDD 小端) + 保留(uint32=0) + 值(float32 小端)
# 数据基于平均股价指数 880003，全市场个股 TR 突破占比(%)。
# 阈值参考：沸点 87（超买）、相变 50（多空分界）、冰点 13（超卖）。
import json, os, sys, struct, subprocess, datetime, tempfile

BASE = "/Users/sugieliao/WorkBuddy/A股每日复盘"
DATA = os.path.join(BASE, "data")
OUT = os.path.join(DATA, "tr_emotion.json")
PRLCTL = "/usr/local/bin/prlctl"
VM_NAME = "Windows 11 Pro"
TDX_PATH = r"C:\new_tdx64\T0002\extdata"
# Parallels 共享目录映射：Mac /Users/sugieliao/ → Windows C:\Mac\Home\
WIN_TMP_DIR = r"C:\Mac\Home"
MAC_HOME = os.path.expanduser("~")
EXT_NUMS = [38, 39, 40]  # 38=HTR10, 39=HTR20, 40=HTR40
EXT_KEYS = {38: "htr10", 39: "htr20", 40: "htr40"}
EXT_LABELS = {38: "HTR10(短期)", 39: "HTR20(中期)", 40: "HTR40(长期)"}


def copy_from_vm(ext_num, local_path):
    """通过 prlctl exec 在 VM 中 copy 文件到 Parallels 共享目录，再在 Mac 端读取。"""
    win_src = f"{TDX_PATH}\\extdata_{ext_num}.dat"
    win_dst = f"{WIN_TMP_DIR}\\__tmp_tr_{ext_num}.dat"
    try:
        r = subprocess.run(
            [PRLCTL, "exec", VM_NAME, "cmd", "/c", f"copy /Y {win_src} {win_dst}"],
            capture_output=True, timeout=30
        )
        if r.returncode != 0:
            err_msg = ""
            try:
                err_msg = (r.stderr or r.stdout).decode("gbk", errors="replace").strip()
            except Exception:
                err_msg = f"returncode={r.returncode}"
            return False, f"prlctl exec 返回码 {r.returncode}: {err_msg}"
    except Exception as e:
        return False, f"prlctl exec 异常: {e}"
    # 共享目录映射：Windows C:\Mac\Home\ → Mac /Users/sugieliao/
    mac_path = os.path.join(MAC_HOME, f"__tmp_tr_{ext_num}.dat")
    if not os.path.exists(mac_path):
        return False, f"复制后文件不存在: {mac_path}"
    import shutil
    shutil.move(mac_path, local_path)
    return True, None


def parse_ext(local_path):
    """解析扩展数据二进制文件，返回 [(date_str, value), ...]"""
    with open(local_path, "rb") as f:
        raw = f.read()
    n = len(raw) // 12
    records = []
    for i in range(n):
        off = i * 12
        date_raw, reserved, val = struct.unpack_from("<IIf", raw, off)
        if date_raw == 0:
            continue
        y, m, d = date_raw // 10000, (date_raw // 100) % 100, date_raw % 100
        date_str = f"{y}-{m:02d}-{d:02d}"
        records.append((date_str, round(val, 4)))
    return records


def main():
    # 临时目录存放从 VM 复制的 dat 文件
    tmp_dir = tempfile.mkdtemp(prefix="tr_emotion_")
    try:
        all_series = {}
        for num in EXT_NUMS:
            local_path = os.path.join(tmp_dir, f"extdata_{num}.dat")
            ok, err = copy_from_vm(num, local_path)
            if not ok:
                # 失败保护：保留旧数据不覆盖
                if os.path.exists(OUT):
                    try:
                        old = json.load(open(OUT, encoding="utf-8"))
                        if old.get("ok") and old.get("dates"):
                            print(f"[tr_emotion] extdata_{num} 取数失败（{err}），"
                                  f"保留上次数据（截至 {old['dates'][-1]}），不覆盖。")
                            return
                    except Exception:
                        pass
                out = {"ok": False, "reason": f"extdata_{num} 取数失败: {err}",
                       "updated": datetime.date.today().strftime("%Y-%m-%d")}
                json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                print(f"[tr_emotion] 取数失败（{err}），无可用旧数据，已写 ok:false 占位。")
                return
            records = parse_ext(local_path)
            all_series[EXT_KEYS[num]] = records
            print(f"[tr_emotion] extdata_{num}({EXT_LABELS[num]}): {len(records)} 条, "
                  f"{records[0][0]} → {records[-1][0]}")

        # 按日期对齐三个序列（日期应该完全一致，以防万一做对齐）
        date_set = None
        for key in EXT_KEYS.values():
            dates = {d for d, _ in all_series[key]}
            date_set = dates if date_set is None else date_set & dates
        common_dates = sorted(date_set)
        # 构建各序列的值数组（按 common_dates 对齐）
        val_map = {}
        for key in EXT_KEYS.values():
            m = {d: v for d, v in all_series[key]}
            val_map[key] = [m[d] for d in common_dates]

        out = {
            "ok": True,
            "source": "通达信扩展数据 38/39/40（TR占比 日线，基于平均股价指数880003）",
            "updated": datetime.date.today().strftime("%Y-%m-%d"),
            "dates": common_dates,
            "htr10": val_map["htr10"],
            "htr20": val_map["htr20"],
            "htr40": val_map["htr40"],
            "thresholds": {"boiling": 87, "phase": 50, "freezing": 13},
        }
        json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        last = common_dates[-1]
        print(f"[tr_emotion] 已写 {len(common_dates)} 个交易日 TR情绪，范围 {common_dates[0]} → {last}；"
              f"最新 HTR10={val_map['htr10'][-1]:.2f} HTR20={val_map['htr20'][-1]:.2f} "
              f"HTR40={val_map['htr40'][-1]:.2f}")
    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # 确保共享目录中的临时文件也被清理
        for num in EXT_NUMS:
            p = os.path.join(MAC_HOME, f"__tmp_tr_{num}.dat")
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
