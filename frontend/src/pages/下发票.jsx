import React, { useEffect, useState } from "react";
import { get, postFixture } from "../api.js";

export default function 下发票() {
  const [rows, setRows] = useState([]);
  const [讯, set讯] = useState("");
  const 刷 = async () => setRows(await get("/下发票"));
  useEffect(() => { 刷().catch((e) => set讯(String(e))); }, []);

  const 取边缘 = async (版本键) => {
    try {
      const r = await get(`/边缘载荷/${encodeURIComponent(版本键)}`);
      set讯(`出站 ${版本键}：${JSON.stringify(r.载荷)}${r.是否补齐 ? "（补齐载荷）" : ""}`);
    } catch (e) {
      set讯(`失败闭 ${版本键}：${e.message}（空洞载荷不得出站）`);
    }
  };

  return (
    <div>
      <h1 className="题">下发票</h1>
      <p className="述">
        版本对分桶的一次灰度下发。出票前先过变体契约核证——空洞/无效载荷直接失败闭，不留下发票行。
      </p>
      <div className="行">
        <button onClick={async () => { await postFixture("下发样例"); await 刷(); set讯("已灌下发样例"); }}>灌下发样例</button>
        <button className="次" onClick={() => 刷()}>刷新</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
      {!rows.length ? <div className="空态">尚无下发票（需先入轨+分桶）</div> : (
        <table>
          <thead><tr><th>票号</th><th>版本键</th><th>桶键</th><th>状态</th><th>下发时</th><th>下发读路径</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.票号}>
              <td>{r.票号}</td><td>{r.版本键}</td><td>{r.桶键}</td>
              <td><span className="徽章 通">{r.状态}</span></td><td>{r.下发时}</td>
              <td><button className="次" onClick={() => 取边缘(r.版本键)}>边缘取载荷</button></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
