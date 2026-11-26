import React, { useEffect, useState } from "react";
import { get, post, postFixture } from "../api.js";

export default function 开关轨() {
  const [rows, setRows] = useState([]);
  const [讯, set讯] = useState("");
  const [边讯, set边讯] = useState("");
  const 刷 = async () => setRows(await get("/开关版本"));
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 看边缘 = async (版本键) => {
    set边讯("");
    try {
      const r = await get(`/边缘载荷/${encodeURIComponent(版本键)}`);
      set边讯(`出站载荷 ${版本键}：variant=${r.变体}${r.是否补齐 ? "（默认补齐）" : ""} valid=${r.valid}`);
    } catch (e) {
      set边讯(`失败闭 ${版本键}：${e.message}`);
    }
  };

  return (
    <div>
      <h1 className="题">开关轨</h1>
      <p className="述">
        开关版本入轨。多变体开关契约要求 variant 必填：缺字段按契约口径「补齐默认变体」或「拒收」；
        补齐版本带标记，边缘只读出站有效载荷。
      </p>
      <div className="行">
        <button onClick={async () => { await postFixture("入轨样例"); await 刷(); set讯("已灌入轨样例"); }}>灌入轨样例</button>
        <button onClick={async () => { await postFixture("入轨缺变体样例"); await 刷(); set讯("缺字段→默认 A 补齐入轨"); }}>灌缺变体（补齐）</button>
        <button onClick={async () => { await postFixture("入轨完整样例"); await 刷(); set讯("完整字段对照，不补齐"); }}>灌完整对照</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {边讯 && <p className="讯">{边讯}</p>}
      {!rows.length ? <div className="空态">尚无版本，先灌入轨样例</div> : (
        <table>
          <thead><tr>
            <th>版本键</th><th>开关键</th><th>版本号</th><th>状态</th>
            <th>variant</th><th>补齐</th><th>valid</th><th>违约原因</th><th>入轨时</th><th>边缘读</th>
          </tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.版本键}>
              <td>{r.版本键}</td><td>{r.开关键}</td><td>{r.版本号}</td>
              <td><span className="徽章 通">{r.状态}</span></td>
              <td><code>{r.变体 ?? (r.载荷?.variant ?? "—")}</code></td>
              <td>{r.补齐 ? <span className="徽章 信">默认补齐·{r.默认变体}</span> : <span className="徽章 通">原样</span>}</td>
              <td>{r.valid === undefined ? "—" : (r.valid ? <span className="徽章 通">true</span> : <span className="徽章 败">false</span>)}</td>
              <td>{r.违约原因 || "—"}</td>
              <td>{r.入轨时}</td>
              <td><button className="次" onClick={() => 看边缘(r.版本键)}>取载荷</button></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
