"""变体必填准入。

落地口径（与入轨同成败，单事务原子）：
- 物化契约表 ``变体契约``：每个多变体开关一行，带 ``默认变体`` 列与准入口径
  （``补齐`` / ``拒收``）。
- 缺 ``variant`` 字段的入轨门二选一：
  * 补齐口径：可入轨，但载荷写入默认 variant，并落补齐标记；
  * 拒收口径：失败闭——回滚整批，无版本行、无核证行。
- 核证表 ``变体核证`` 记录是否补齐、补齐后载荷快照、违约原因、valid。
- 下发读路径（边缘取载荷）失败闭：无契约/核证/有效 variant 一律拒绝，
  空洞载荷不得静默出站。
"""

import json
from datetime import datetime, timezone

from fastapi import HTTPException

补齐 = "补齐"
拒收 = "拒收"
支持口径 = (补齐, 拒收)
变体字段 = "variant"


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 取契约(conn, 开关键: str):
    return conn.execute(
        "SELECT * FROM 变体契约 WHERE 开关键=? AND 启用=1", (开关键,)
    ).fetchone()


def 写契约(conn, 体: dict) -> dict:
    开关键 = 体["开关键"]
    口径 = 体.get("准入口径", 补齐)
    if 口径 not in 支持口径:
        raise HTTPException(400, f"未知准入口径:{口径}（支持 {支持口径}）")
    默认变体 = str(体.get("默认变体", "A")).strip()
    if not 默认变体:
        raise HTTPException(400, "默认变体不得为空")
    必填 = 1 if 体.get("必填变体", True) else 0
    启用 = 1 if 体.get("启用", True) else 0
    conn.execute(
        """INSERT INTO 变体契约(开关键, 必填变体, 默认变体, 准入口径, 启用, 更新时)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(开关键) DO UPDATE SET
             必填变体=excluded.必填变体, 默认变体=excluded.默认变体,
             准入口径=excluded.准入口径, 启用=excluded.启用, 更新时=excluded.更新时""",
        (开关键, 必填, 默认变体, 口径, 启用, 此刻()),
    )
    return {
        "开关键": 开关键,
        "必填变体": bool(必填),
        "默认变体": 默认变体,
        "准入口径": 口径,
        "启用": bool(启用),
    }


def _记核证(conn, 版本键: str, 开关键: str, *, 补齐否: bool, 有效: bool,
            变体: str, 契约, 原因: str, 快照: dict) -> None:
    conn.execute(
        """INSERT INTO 变体核证
             (版本键, 开关键, 是否补齐, 是否有效, 变体, 默认变体, 准入口径,
              违约原因, 载荷快照, 时刻)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(版本键) DO UPDATE SET
             是否补齐=excluded.是否补齐, 是否有效=excluded.是否有效,
             变体=excluded.变体, 违约原因=excluded.违约原因,
             载荷快照=excluded.载荷快照, 时刻=excluded.时刻""",
        (
            版本键, 开关键, 1 if 补齐否 else 0, 1 if 有效 else 0,
            变体, 契约["默认变体"] if 契约 is not None else "",
            契约["准入口径"] if 契约 is not None else "",
            原因, json.dumps(快照, ensure_ascii=False), 此刻(),
        ),
    )


def 准入(conn, 版本键: str, 开关键: str, 载荷: dict) -> dict:
    """对单个版本执行契约校验，返回核证结论。

    调用方（入轨服务）须在同一连接/事务内先调本函数再写版本行；
    拒收口径抛 ``HTTPException`` 时，调用方不得 commit——版本行与核证行
    均随回滚消失，保证「契约与入轨同成败」。
    """
    契约 = 取契约(conn, 开关键)
    变体值 = 载荷.get(变体字段)
    缺字段 = 变体值 is None or (isinstance(变体值, str) and not 变体值.strip())
    原因 = ""

    # 无契约或契约未要求变体：不参与本闸，按非多变体开关放行，仍留核证以便观测
    if 契约 is None or not 契约["必填变体"]:
        _记核证(
            conn, 版本键, 开关键, 补齐否=False, 有效=not 缺字段,
            变体=("" if 缺字段 else str(变体值)), 契约=契约,
            原因=("" if not 缺字段 else "无契约约束的空变体"),
            快照=载荷,
        )
        return {"是否补齐": False, "valid": not 缺字段, "变体": 变体值,
                "默认变体": "", "准入口径": "", "违约原因": "" if not 缺字段 else "无契约约束的空变体"}

    if not 缺字段:
        _记核证(
            conn, 版本键, 开关键, 补齐否=False, 有效=True,
            变体=str(变体值), 契约=契约, 原因="", 快照=载荷,
        )
        return {"是否补齐": False, "valid": True, "变体": str(变体值),
                "默认变体": 契约["默认变体"], "准入口径": 契约["准入口径"],
                "违约原因": ""}

    # 命中违约：缺 variant 字段
    原因 = f"缺变体字段:{开关键}"
    if 契约["准入口径"] == 拒收:
        # 失败闭：不落版本行、不落核证行，整批回滚由调用方 commit 边界保证
        raise HTTPException(400, f"变体必填拒收:{原因}（口径=拒收，无默认补齐）")

    # 补齐口径：以默认变体写入载荷，落补齐标记；下发/回读见到的是补齐后载荷
    补齐值 = 契约["默认变体"]
    载荷[变体字段] = 补齐值
    _记核证(
        conn, 版本键, 开关键, 补齐否=True, 有效=True,
        变体=补齐值, 契约=契约, 原因=原因, 快照=载荷,
    )
    return {"是否补齐": True, "valid": True, "变体": 补齐值,
            "默认变体": 补齐值, "准入口径": 补齐, "违约原因": 原因}


def 边缘读载荷(conn, 版本键: str) -> dict:
    """下发读路径取载荷——失败闭，空洞载荷不得出站。"""
    ver = conn.execute(
        "SELECT * FROM 开关版本 WHERE 版本键=?", (版本键,)
    ).fetchone()
    if not ver:
        raise HTTPException(400, f"版本未入轨:{版本键}")
    try:
        载荷 = json.loads(ver["载荷"])
    except (TypeError, ValueError):
        raise HTTPException(400, f"载荷不可解析，失败闭:{版本键}")
    if not isinstance(载荷, dict):
        raise HTTPException(400, f"载荷非对象，失败闭:{版本键}")

    核 = conn.execute(
        "SELECT * FROM 变体核证 WHERE 版本键=?", (版本键,)
    ).fetchone()
    契约 = 取契约(conn, ver["开关键"])
    if 契约 is not None and 契约["必填变体"]:
        if 核 is None:
            raise HTTPException(400, f"缺核证记录，失败闭:{版本键}")
        if not 核["是否有效"]:
            raise HTTPException(400, f"核证 invalid，失败闭:{版本键}:{核['违约原因']}")
        变体 = 载荷.get(变体字段)
        if 变体 is None or (isinstance(变体, str) and not 变体.strip()):
            # 空洞载荷：直接失败，禁止静默空字段出站
            raise HTTPException(400, f"空洞变体载荷，失败闭:{版本键}")
    return {
        "版本键": 版本键,
        "开关键": ver["开关键"],
        "载荷": 载荷,
        "是否补齐": bool(核["是否补齐"]) if 核 else False,
        "变体": (核["变体"] if 核 else 载荷.get(变体字段, "")),
        "valid": bool(核["是否有效"]) if 核 else True,
    }
