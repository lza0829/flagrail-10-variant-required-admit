"""变体必填准入核证脚本。

覆盖：
1. 缺字段入轨（补齐口径）——可入轨，写入默认 variant + 补齐标记，
   边缘/回读见到补齐后载荷；
2. 完整字段对照——不补齐；
3. 拒收口径——失败闭：无版本行、无核证行、批次无报告；
4. 空洞载荷不得出站——绕过准入直写空洞版本后，下发与边缘读均 400；
5. 违约入轨与下发并发交错——下发永远读不到空洞载荷；
6. 贯验纳入契约三联互证。

运行：PYTHONPATH=backend python -I backend/tests/test_变体必填准入.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 隔离数据目录，必须在 import app.* 之前设置
_tmp = tempfile.mkdtemp(prefix="flagrail-test-")
os.environ["数据目录"] = _tmp
os.environ["夹具目录"] = str(Path(__file__).resolve().parent.parent.parent / "fixtures")

from fastapi import HTTPException  # noqa: E402

from app import seed  # noqa: E402
from app.db import 连接  # noqa: E402
from app.modules import 变体必填准入  # noqa: E402
from app.services import 入轨, 下发, 分桶, 贯验  # noqa: E402

开关 = "checkout.new_tax"


class 变体必填准入测试(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.初始化库()

    def _版本行(self, 版本键):
        conn = 连接()
        try:
            return conn.execute(
                "SELECT * FROM 开关版本 WHERE 版本键=?", (版本键,)
            ).fetchone()
        finally:
            conn.close()

    def _核证行(self, 版本键):
        conn = 连接()
        try:
            return conn.execute(
                "SELECT * FROM 变体核证 WHERE 版本键=?", (版本键,)
            ).fetchone()
        finally:
            conn.close()

    def _切口径(self, 口径, 默认变体="A"):
        conn = 连接()
        try:
            变体必填准入.写契约(conn, {
                "开关键": 开关, "准入口径": 口径,
                "默认变体": 默认变体, "必填变体": True,
            })
            conn.commit()
        finally:
            conn.close()

    def test_01_缺字段补齐入轨(self):
        self._切口径(变体必填准入.补齐)
        版本键 = f"{开关}@101"
        报 = 入轨.入一批({
            "批次编号": "批-补齐",
            "版本": [{"开关键": 开关, "版本号": 101, "载荷": {"enabled": True}}],
        })
        # 入轨成功，报告带核证
        self.assertEqual(报["报告"]["写入"], 1)
        self.assertEqual(报["报告"]["补齐"], 1)
        行 = self._版本行(版本键)
        self.assertIsNotNone(行, "补齐口径必须有版本行")
        载荷 = json.loads(行["载荷"])
        self.assertEqual(载荷.get("variant"), "A", "载荷必须写入默认 variant")
        核 = self._核证行(版本键)
        self.assertIsNotNone(核, "补齐版本必须有核证行")
        self.assertTrue(核["是否补齐"])
        self.assertTrue(核["是否有效"])
        self.assertEqual(核["变体"], "A")
        self.assertIn("缺变体字段", 核["违约原因"])
        # 快照即补齐后载荷
        self.assertEqual(json.loads(核["载荷快照"]).get("variant"), "A")

    def test_02_完整字段对照不补齐(self):
        版本键 = f"{开关}@102"
        入轨.入一批({
            "批次编号": "批-对照",
            "版本": [{"开关键": 开关, "版本号": 102,
                     "载荷": {"enabled": True, "variant": "C"}}],
        })
        行 = self._版本行(版本键)
        self.assertEqual(json.loads(行["载荷"])["variant"], "C")
        核 = self._核证行(版本键)
        self.assertFalse(核["是否补齐"], "自带变体不得标补齐")
        self.assertTrue(核["是否有效"])
        self.assertEqual(核["违约原因"], "")

    def test_03_拒收口径失败闭无版本行(self):
        self._切口径(变体必填准入.拒收)
        版本键 = f"{开关}@103"
        with self.assertRaises(HTTPException) as cm:
            入轨.入一批({
                "批次编号": "批-拒收",
                "版本": [{"开关键": 开关, "版本号": 103,
                         "载荷": {"enabled": True}}],
            })
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIsNone(self._版本行(版本键), "拒收必须无版本行")
        self.assertIsNone(self._核证行(版本键), "拒收必须无核证行")
        conn = 连接()
        try:
            批 = conn.execute(
                "SELECT 1 FROM 装载批次 WHERE 编号=?", ("批-拒收",)
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(批, "拒收批次不得留批次报告")
        # 观测点可区分：拒收后版本不存在；补齐版本（101）存在且含默认 variant
        self.assertIsNone(self._版本行(版本键))
        self.assertIsNotNone(self._版本行(f"{开关}@101"))
        self._切口径(变体必填准入.补齐)

    def test_04_空洞载荷下发与边缘读双失败闭(self):
        # 先正常入轨一个版本，再模拟缺陷把载荷改空（绕过准入的脏数据）
        版本键 = f"{开关}@104"
        入轨.入一批({
            "批次编号": "批-空洞",
            "版本": [{"开关键": 开关, "版本号": 104,
                     "载荷": {"enabled": True, "variant": "B"}}],
        })
        分桶.写桶({
            "桶键": f"{开关}-桶104", "开关键": 开关,
            "桶类型": "百分比", "规则": {"percent": 10},
        })
        conn = 连接()
        try:
            conn.execute(
                "UPDATE 开关版本 SET 载荷=? WHERE 版本键=?",
                (json.dumps({"enabled": True}, ensure_ascii=False), 版本键),
            )
            conn.commit()
        finally:
            conn.close()
        # 边缘读直接失败，不静默空字段出站
        with self.assertRaises(HTTPException) as cm:
            下发.取边缘载荷(版本键)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("空洞", cm.exception.detail)
        # 下发同票失败闭：空洞载荷不得出票
        with self.assertRaises(HTTPException) as cm2:
            下发.下一票({
                "票号": f"票-{版本键}-桶104", "版本键": 版本键,
                "桶键": f"{开关}-桶104",
            })
        self.assertEqual(cm2.exception.status_code, 400)
        conn = 连接()
        try:
            票 = conn.execute(
                "SELECT 1 FROM 下发票 WHERE 票号=?",
                (f"票-{版本键}-桶104",),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(票, "失败闭不得留下发票行")

    def test_05_违约入轨与下发交错读不到空洞(self):
        # 拒收口径下，缺字段入轨与下发并发交错：入轨整体失败，下发必然报版本未入轨
        self._切口径(变体必填准入.拒收)
        版本键 = f"{开关}@105"
        try:
            入轨.入一批({
                "批次编号": "批-交错",
                "版本": [{"开关键": 开关, "版本号": 105,
                         "载荷": {"enabled": True}}],
            })
        except HTTPException:
            pass
        分桶.写桶({
            "桶键": f"{开关}-桶105", "开关键": 开关,
            "桶类型": "百分比", "规则": {"percent": 10},
        })
        with self.assertRaises(HTTPException) as cm:
            下发.下一票({
                "票号": f"票-{版本键}-桶105", "版本键": 版本键,
                "桶键": f"{开关}-桶105",
            })
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("未入轨", cm.exception.detail)
        self._切口径(变体必填准入.补齐)

    def test_06_补齐版本全链可下发且边缘见补齐载荷(self):
        版本键 = f"{开关}@101"  # test_01 的补齐版本
        分桶.写桶({
            "桶键": f"{开关}-桶101", "开关键": 开关,
            "桶类型": "百分比", "规则": {"percent": 10},
        })
        票 = 下发.下一票({
            "票号": f"票-{版本键}-桶101", "版本键": 版本键,
            "桶键": f"{开关}-桶101",
        })
        self.assertEqual(票["状态"], "已下发")
        边 = 下发.取边缘载荷(版本键)
        self.assertEqual(边["载荷"]["variant"], "A", "回读必须见补齐后载荷")
        self.assertTrue(边["是否补齐"])
        self.assertTrue(边["valid"])

    def test_07_贯验纳入契约三联(self):
        报 = 贯验.跑贯验()
        # 104 是人为制造的空洞版本，贯验必须抓到
        self.assertFalse(报["是否通过"])
        self.assertIn("空洞变体载荷:checkout.new_tax@104", 报["说明"])

    def test_08_无契约开关不参与本闸(self):
        版本键 = "other.flag@1"
        入轨.入一批({
            "批次编号": "批-无契约",
            "版本": [{"开关键": "other.flag", "版本号": 1,
                     "载荷": {"enabled": False}}],
        })
        self.assertIsNotNone(self._版本行(版本键))
        核 = self._核证行(版本键)
        self.assertFalse(核["是否有效"], "无契约约束的空变体核证 valid=False 留痕")


if __name__ == "__main__":
    unittest.main(verbosity=2)
