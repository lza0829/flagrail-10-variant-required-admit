import React, { useEffect, useState } from "react";
import { get, post } from "../api.js";

const 空表单 = { 开关键: "checkout.new_tax", 默认变体: "A", 准入口径: "补齐", 必填变体: true, 启用: true };

export default function 变体契约页() {
  const [契约, set契约] = useState([]);
  const [核证, set核证] = useState([]);
  const [表单, set表单] = useState(空表单);
  const [讯, set讯] = useState("");
  const 刷 = async () => {
    set契约(await get("/变体契约"));
    set核证(await get("/变体核证"));
  };
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 提交 = async () => {
    set讯("");
    try {
      const r = await post("/变体契约", 表单);
      set讯(`契约已写：${r.开关键} 口径=${r.准入口径} 默认=${r.默认变体}`);
      await 刷();
    } catch (e) {
      set讯(String(e));
    }
  };

  return (
    <div>
      <h1 className="题">变体契约 · 核证</h1>
      <p className="述">
        物化契约表约束多变体开关：variant 必填。缺字段准入口径二选——「补齐」写默认变体并落补齐标记；
        「拒收」失败闭、无版本行。核证记录补齐、载荷快照、违约原因与 valid。
      </p>
      <div className="提示条">
        观测点：拒收口径下缺字段版本<span className="mono">不存在</span>；补齐口径下版本存在且
        <span className="mono">含默认 variant + 补齐标记</span>——两者可区分。
      </div>

      <h2 className="题" style={{ fontSize: "1rem" }}>写契约</h2>
      <div className="行">
        <label>开关键
          <input value={表单.开关键} onChange={(e) => set表单({ ...表单, 开关键: e.target.value })} />
        </label>
        <label>默认变体
          <input value={表单.默认变体} style={{ width: 90 }}
            onChange={(e) => set表单({ ...表单, 默认变体: e.target.value })} />
        </label>
        <label>准入口径
          <select value={表单.准入口径} onChange={(e) => set表单({ ...表单, 准入口径: e.target.value })}>
            <option value="补齐">补齐（默认变体）</option>
            <option value="拒收">拒收（失败闭）</option>
          </select>
        </label>
        <label>必填
          <input type="checkbox" checked={表单.必填变体}
            onChange={(e) => set表单({ ...表单, 必填变体: e.target.checked })} />
        </label>
        <button className="信" onClick={提交}>写契约</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}

      <h2 className="题" style={{ fontSize: "1rem", marginTop: "1.2rem" }}>契约表</h2>
      {!契约.length ? <div className="空态">尚无契约</div> : (
        <table>
          <thead><tr><th>开关键</th><th>必填</th><th>默认变体</th><th>准入口径</th><th>启用</th><th>更新时</th></tr></thead>
          <tbody>{契约.map((r) => (
            <tr key={r.开关键}>
              <td>{r.开关键}</td>
              <td>{r.必填变体 ? <span className="徽章 败">必填</span> : <span className="徽章 通">否</span>}</td>
              <td><code>{r.默认变体}</code></td>
              <td><span className={"徽章 " + (r.准入口径 === "拒收" ? "败" : "信")}>{r.准入口径}</span></td>
              <td>{r.启用 ? "是" : "否"}</td><td>{r.更新时}</td>
            </tr>
          ))}</tbody>
        </table>
      )}

      <h2 className="题" style={{ fontSize: "1rem", marginTop: "1.2rem" }}>核证路由</h2>
      {!核证.length ? <div className="空态">尚无核证</div> : (
        <table>
          <thead><tr>
            <th>版本键</th><th>补齐</th><th>valid</th><th>变体</th>
            <th>口径</th><th>违约原因</th><th>载荷快照</th><th>时刻</th>
          </tr></thead>
          <tbody>{核证.map((r) => (
            <tr key={r.版本键}>
              <td>{r.版本键}</td>
              <td>{r.是否补齐 ? <span className="徽章 信">补齐</span> : <span className="徽章 通">否</span>}</td>
              <td>{r.是否有效 ? <span className="徽章 通">true</span> : <span className="徽章 败">false</span>}</td>
              <td><code>{r.变体 || "—"}</code></td>
              <td>{r.准入口径 || "—"}</td>
              <td>{r.违约原因 || "—"}</td>
              <td><code>{JSON.stringify(r.载荷快照)}</code></td>
              <td>{r.时刻}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
