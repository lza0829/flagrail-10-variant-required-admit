import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db import 连接
from app.modules import 变体必填准入


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 入一批(体: dict) -> dict:
    批次 = 体.get("批次编号") or f"入轨-{此刻()}"
    版本们 = 体.get("版本") or []
    conn = 连接()
    写入 = 0
    跳过 = 0
    补齐 = 0
    核证们 = []
    try:
        for v in 版本们:
            开关键 = v["开关键"]
            版本号 = int(v["版本号"])
            版本键 = v.get("版本键") or f"{开关键}@{版本号}"
            载荷 = v.get("载荷", {})
            if not isinstance(载荷, dict):
                # 契约校验只认对象载荷；非对象直接失败闭，避免空洞载荷入轨
                raise HTTPException(400, f"载荷必须为对象:{版本键}")
            已 = conn.execute("SELECT 1 FROM 开关版本 WHERE 版本键=?", (版本键,)).fetchone()
            if 已:
                跳过 += 1
                continue
            # 契约校验与版本行同票：拒收口径在此抛错，整批回滚，无版本行无核证行
            证 = 变体必填准入.准入(conn, 版本键, 开关键, 载荷)
            载荷文 = json.dumps(载荷, ensure_ascii=False)
            conn.execute(
                "INSERT INTO 开关版本(版本键, 开关键, 版本号, 载荷, 状态, 入轨时, 说明) VALUES (?,?,?,?,?,?,?)",
                (版本键, 开关键, 版本号, 载荷文, "已入轨", 此刻(), v.get("说明", "")),
            )
            写入 += 1
            if 证["是否补齐"]:
                补齐 += 1
            核证们.append({"版本键": 版本键, **证})
        报告 = {
            "写入": 写入, "跳过": 跳过, "补齐": 补齐,
            "核证": 核证们, "类型": "入轨",
        }
        conn.execute(
            "INSERT OR REPLACE INTO 装载批次(编号, 时刻, 报告) VALUES (?,?,?)",
            (批次, 此刻(), json.dumps(报告, ensure_ascii=False)),
        )
        conn.commit()
        return {"批次编号": 批次, "报告": 报告}
    except Exception:
        # 失败闭：任何一步违约，整票回滚——契约与入轨同成败
        conn.rollback()
        raise
    finally:
        conn.close()
