
// ===== 静态模式：fetch 重写 =====
const ORIG_FETCH = window.fetch.bind(window);
window.fetch = async function(url, ...args) {
    if (typeof url !== "string") return ORIG_FETCH(url, ...args);
    let m;
    if (m = url.match(/^\/api\/review\?date=(\d+)/)) {
        url = `./data/review_${m[1]}.json`;
    } else if (url.startsWith("/api/trade_dates")) {
        url = "./data/trade_dates.json";
    } else if (m = url.match(/^\/api\/lhb\/(\d+)/)) {
        url = `./data/lhb_${m[1]}.json`;
    } else if (m = url.match(/^\/api\/concept_flow\/(\d+)/)) {
        url = `./data/concept_flow_${m[1]}.json`;
    } else if (url.startsWith("/api/north_flow")) {
        url = "./data/north_flow.json";
    } else if (m = url.match(/^\/api\/youzi_trace\/(\d+)/)) {
        url = `./data/youzi_trace_${m[1]}.json`;
    }
    try {
        const res = await ORIG_FETCH(url, ...args);
        if (!res.ok) {
            return new Response(JSON.stringify({code: 0, data: {}}),
                {status: 200, headers: {"Content-Type": "application/json"}});
        }
        return res;
    } catch (e) {
        return new Response(JSON.stringify({code: 0, data: {}}),
            {status: 200, headers: {"Content-Type": "application/json"}});
    }
};
const API = "/api/review";

// ---------- 主题相关 ----------
function chartTheme() {
    return document.documentElement.dataset.theme === "light" ? "" : "dark";
}
function chartColor(key) {
    const light = document.documentElement.dataset.theme === "light";
    const map = {
        axis:  light ? "#6b7280" : "#9ca3af",
        line:  light ? "#e2e4e8" : "#2a2d35",
        label: light ? "#1f2328" : "#d1d5db",
        text:  light ? "#1f2328" : "#e0e0e0",
    };
    return map[key] || "#9ca3af";
}
function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("theme", t); } catch (e) {}
    const btn = document.getElementById("themeBtn");
    if (btn) btn.textContent = t === "light" ? "🌙 暗色" : "☀️ 亮色";
    // 重建 ECharts 主题
    if (themeChart)   { themeChart.dispose();   themeChart = null; }
    if (lianbanChart) { lianbanChart.dispose(); lianbanChart = null; }
    if (mChart)       { mChart.dispose();       mChart = null; }
    if (typeof lastMetrics !== "undefined" && lastMetrics) {
        renderThemeChart(lastMetrics.theme_dist || {});
        renderLianbanChart(lastMetrics.lianban_tiers || {});
    }
    if (typeof mChartData !== "undefined" && mChartData &&
        document.getElementById("stockModal") &&
        !document.getElementById("stockModal").classList.contains("hidden")) {
        mChart = echarts.init(document.getElementById("mChart"), chartTheme());
        if (typeof drawChart === "function") drawChart(mChartKind);
    }
}
// 启动时读取
(function initTheme() {
    let t = "dark";
    try { t = localStorage.getItem("theme") || "dark"; } catch (e) {}
    document.documentElement.dataset.theme = t;
    document.addEventListener("DOMContentLoaded", () => {
        const btn = document.getElementById("themeBtn");
        if (btn) {
            btn.textContent = t === "light" ? "🌙 暗色" : "☀️ 亮色";
            btn.addEventListener("click", () => {
                const cur = document.documentElement.dataset.theme === "light" ? "dark" : "light";
                applyTheme(cur);
            });
        }
    });
})();


// ============================================================
// 全局开关：是否启用个股详情弹窗（分时/K线/盘口）
// true  = 点击股票打开弹窗
// false = 点击股票不做任何事（禁用弹窗）
// ============================================================
const ENABLE_STOCK_MODAL = false;
let themeChart = null, lianbanChart = null, fp = null;
let currentDate = null;
const $ = (id) => document.getElementById(id);

const tableState = {
  ztTable: { data: [], sortIndex: -1, sortDir: "desc",
    columns: [
      {key:"code",type:"str"},{key:"name",type:"str"},{key:"pct_chg",type:"num"},
      {key:"consecutive_days",type:"num"},{key:"industry",type:"str"},
      {key:"seal_amount",type:"num"},{key:"turnover",type:"num"},
      {key:"first_seal_time",type:"str"},{key:"break_count",type:"num"}],
    renderRow:(s)=>`<td>${s.code||""}</td><td>${s.name||""}</td><td>${pctHtml(s.pct_chg)}</td><td><span class="tag tag-red">${s.consecutive_days||1}</span></td><td class="col-ellipsis col-industry"><span class="tag">${s.industry||"-"}</span></td><td class="num-col">${fmtMoney(s.seal_amount)}</td><td class="num-col">${num2(s.turnover,"%")}</td><td>${s.first_seal_time||"-"}</td><td class="num-col">${s.break_count!=null?s.break_count:"-"}</td>` },
  zbTable: { data: [], sortIndex: -1, sortDir: "desc",
    columns: [
      {key:"code",type:"str"},{key:"name",type:"str"},{key:"pct_chg",type:"num"},
      {key:"industry",type:"str"},{key:"break_count",type:"num"},{key:"first_seal_time",type:"str"}],
    renderRow:(s)=>`<td>${s.code||""}</td><td>${s.name||""}</td><td>${pctHtml(s.pct_chg)}</td><td class="col-ellipsis col-industry"><span class="tag">${s.industry||"-"}</span></td><td class="num-col">${s.break_count!=null?s.break_count:"-"}</td><td>${s.first_seal_time||"-"}</td>` },
  dtTable: { data: [], sortIndex: -1, sortDir: "desc",
    columns: [
      {key:"code",type:"str"},{key:"name",type:"str"},{key:"pct_chg",type:"num"},
      {key:"consecutive_days",type:"num"},{key:"industry",type:"str"}],
    renderRow:(s)=>`<td>${s.code||""}</td><td>${s.name||""}</td><td>${pctHtml(s.pct_chg)}</td><td><span class="tag">${s.consecutive_days||1}</span></td><td class="col-ellipsis col-industry"><span class="tag">${s.industry||"-"}</span></td>` },
  lhbTable: { data: [], sortIndex: -1, sortDir: "desc",
    columns: [
      {key:"code",type:"str"},{key:"name",type:"str"},{key:"reason",type:"str"},
      {key:"net_buy",type:"num"},{key:"buy_amount",type:"num"},{key:"sell_amount",type:"num"},
      {key:"pct_chg",type:"num"},{key:"turnover",type:"num"}],
    renderRow:(r)=>{const cls=r.net_buy>0?"text-up":r.net_buy<0?"text-down":"text-muted";const rsn=(r.reason||"").replace(/"/g,"&quot;");return `<td>${r.code||""}</td><td>${r.name||""}</td><td class="col-ellipsis col-reason" title="${rsn}">${r.reason||"-"}</td><td class="num-col ${cls}">${fmtMoney(r.net_buy)}</td><td class="num-col">${fmtMoney(r.buy_amount)}</td><td class="num-col">${fmtMoney(r.sell_amount)}</td><td>${pctHtml(r.pct_chg)}</td><td class="num-col">${num2(r.turnover,"%")}</td>`} },
};

(async function init() {
  initTabs();
  initSortableHeaders();
  initReloadButtons();
  await initDatePicker();
  $("loadBtn").addEventListener("click", () => loadData(false));
  $("refreshBtn").addEventListener("click", () => loadData(true));
  loadData(false);
})();

function initTabs() {
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "panel-" + tab));
      if (tab === "overview") setTimeout(() => { themeChart && themeChart.resize(); lianbanChart && lianbanChart.resize(); }, 30);
    });
  });
}

function initReloadButtons() {
  document.querySelectorAll("[data-reload]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const kind = btn.dataset.reload;
      if (!currentDate) { alert("请先查询日期"); return; }
      const orig = btn.textContent;
      btn.disabled = true; btn.textContent = "刷新中...";
      try {
        const url = `/api/review?date=${currentDate}&refresh=1&only=${kind}`;
        const res = await fetch(url);
        const json = await res.json();
        if (json.code !== 0) throw new Error(json.msg);
        const d = json.data;
        if (kind === "limit") {
          tableState.ztTable.data = d.limit_up_stocks || [];
          tableState.zbTable.data = d.broken_stocks || [];
          tableState.dtTable.data = d.limit_down_stocks || [];
          renderTable("ztTable"); renderTable("zbTable"); renderTable("dtTable");
          $("ztBadge").textContent = tableState.ztTable.data.length;
          $("zbBadge").textContent = tableState.zbTable.data.length;
          $("dtBadge").textContent = tableState.dtTable.data.length;
          updateLimitCount();
        } else if (kind === "lhb") {
          tableState.lhbTable.data = d.dragon_tiger || [];
          renderTable("lhbTable");
          $("cntLhb").textContent = tableState.lhbTable.data.length;
        }
      } catch (e) { alert("刷新失败：" + e.message); }
      finally { btn.disabled = false; btn.textContent = orig; }
    });
  });
}

function initSortableHeaders() {
  Object.entries(tableState).forEach(([tid, st]) => {
    const table = document.querySelector(`#${tid}`);
    if (!table) return;
    document.querySelectorAll(`#${tid} thead th`).forEach((th, i) => {
      if (!st.columns[i]) return;
      th.classList.add("sortable");
      th.addEventListener("click", () => {
        if (st.sortIndex === i) st.sortDir = st.sortDir === "desc" ? "asc" : "desc";
        else { st.sortIndex = i; st.sortDir = "desc"; }
        renderTable(tid); updateArrows(tid);
      });
    });
  });
}
function updateArrows(tid) {
  const st = tableState[tid];
  document.querySelectorAll(`#${tid} thead th`).forEach((th, i) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (i === st.sortIndex) th.classList.add(st.sortDir === "asc" ? "sort-asc" : "sort-desc");
  });
}
function renderTable(tid) {
  const st = tableState[tid];
  const tbody = document.querySelector(`#${tid} tbody`);
  let rows = st.data.slice();
  if (st.sortIndex >= 0 && st.columns[st.sortIndex]) {
    const col = st.columns[st.sortIndex];
    const dir = st.sortDir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      const va = a[col.key], vb = b[col.key];
      if (col.type === "num") {
        const na = Number(va), nb = Number(vb);
        const A = isNaN(na) ? -Infinity : na;
        const B = isNaN(nb) ? -Infinity : nb;
        return (A - B) * dir;
      }
      return String(va ?? "").localeCompare(String(vb ?? ""), "zh", {numeric:true}) * dir;
    });
  }
  tbody.innerHTML = "";
  rows.forEach(r => { const tr = document.createElement("tr"); tr.innerHTML = st.renderRow(r); tbody.appendChild(tr); });
}

async function initDatePicker() {
  const input = $("dateInput");
  let dates = [], latest = new Date().toISOString().slice(0,10).replace(/-/g,"");
  try {
    const res = await fetch("/api/trade_dates");
    const json = await res.json();
    if (json.code === 0 && json.dates && json.dates.length) { dates = json.dates; latest = json.latest || dates[0]; }
  } catch (e) { console.warn("交易日接口失败", e); }
  const toDash = (s) => `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}`;
  const enable = dates.map(toDash);
  const def = toDash(latest);
  if (typeof flatpickr === "undefined") { input.removeAttribute("readonly"); input.type = "date"; input.value = def; return; }
  flatpickr.localize(flatpickr.l10ns.zh);
  fp = flatpickr(input, {
    dateFormat: "Y-m-d", defaultDate: def,
    enable: enable.length ? enable : undefined,
    disableMobile: true, allowInput: false,
    onChange: (sel, str) => { if (str) loadData(false); },
  });
  if (!enable.length) input.removeAttribute("readonly");
}

async function loadData(force) {
  const raw = $("dateInput").value;
  if (!raw) { alert("请选择日期"); return; }
  const d = raw.replace(/-/g, "");
  currentDate = d;
  $("loading").classList.remove("hidden");
  try {
    const url = `${API}?date=${d}${force ? "&refresh=1" : ""}`;
    const res = await fetch(url);
    const json = await res.json();
    if (json.code !== 0) throw new Error(json.msg || "接口异常");
    render(json.data);
  } catch (e) { alert("加载失败：" + e.message); }
  finally { $("loading").classList.add("hidden"); }
}

let lastMetrics = null;
function render(data) {
  const m = data.metrics || {};
  lastMetrics = m;
  setText("ztCount", m.zt_count);
  setText("dtCount", m.dt_count);
  setText("breakRate", (m.break_rate ?? 0).toFixed(2) + "%");
  setText("upCount", m.up_count);
  setText("downCount", m.down_count);

  const yp = m.yesterday_zt_perf || {};
  const avg = yp.avg_pct ?? 0;
  const avgEl = $("yesterdayPerf");
  avgEl.textContent = (avg > 0 ? "+" : "") + Number(avg).toFixed(2) + "%";
  avgEl.className = "card-value " + (avg > 0 ? "text-up" : avg < 0 ? "text-down" : "");
  setText("promoteRate", (yp.promote_rate ?? 0).toFixed(2) + "%");

  const srcMap = {kpl_crawler:"开盘啦", push2:"东财", legu:"乐咕", spot:"全A", none:"-"};
  $("srcBadge").textContent = "数据源：" + (srcMap[m.up_source] || m.up_source || "-");

  renderSentiment(m.sentiment || {});
  renderSectorFlow(data.sector_flow || {});
  loadNorthFlow();
  renderThemeChart(m.theme_dist || {});
  renderLianbanChart(m.lianban_tiers || {});
  renderLianbanBoard(m.theme_groups || []);

  tableState.ztTable.data = data.limit_up_stocks || [];
  tableState.zbTable.data = data.broken_stocks || [];
  tableState.dtTable.data = data.limit_down_stocks || [];
  loadLhbPanel();

  renderTable("ztTable"); updateArrows("ztTable");
  renderTable("zbTable"); updateArrows("zbTable");
  renderTable("dtTable"); updateArrows("dtTable");

  $("ztBadge").textContent = tableState.ztTable.data.length;
  $("zbBadge").textContent = tableState.zbTable.data.length;
  $("dtBadge").textContent = tableState.dtTable.data.length;
  updateLimitCount();
  $("cntLhb").textContent = tableState.lhbTable.data.length;
}

function updateLimitCount() {
  const total = tableState.ztTable.data.length + tableState.zbTable.data.length + tableState.dtTable.data.length;
  const el = $("cntLimit"); if (el) el.textContent = total;
  const bd = $("limitBadge"); if (bd) bd.textContent = total;
}

function setText(id, val) { const el = $(id); if (el) el.textContent = (val == null) ? "-" : val; }
function num2(v, suffix="") { if (v == null || v === "" || isNaN(v)) return "-"; return Number(v).toFixed(2) + suffix; }
function pctHtml(v) {
  if (v == null || v === "" || isNaN(v)) return "-";
  const n = Number(v);
  const cls = n > 0 ? "text-up" : n < 0 ? "text-down" : "text-muted";
  return `<span class="${cls}">${n > 0 ? "+" : ""}${n.toFixed(2)}%</span>`;
}
function fmtMoney(v) {
  if (v == null || v === "" || isNaN(v)) return "-";
  const n = Number(v);
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + "亿";
  if (Math.abs(n) >= 1e4) return Math.round(n / 1e4) + "万";
  return Math.round(n) + "";
}

function renderThemeChart(themeDist) {
  const el = $("themeChart");
  if (!themeChart) themeChart = echarts.init(el, chartTheme());
  const entries = Object.entries(themeDist).sort((a,b)=>b[1]-a[1]).slice(0,15);
  const names = entries.map(e=>e[0]).reverse();
  const values = entries.map(e=>e[1]).reverse();
  themeChart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 110, right: 40, top: 20, bottom: 30 },
    xAxis: { type:"value", axisLabel:{color:chartColor("axis")}, splitLine:{lineStyle:{color:chartColor("line")}} },
    yAxis: { type:"category", data:names, axisLabel:{color:chartColor("label"),fontSize:12}, axisLine:{lineStyle:{color:chartColor("line")}} },
    series: [{ type:"bar", data:values, itemStyle:{color:"#ef4444",borderRadius:[0,4,4,0]}, label:{show:true,position:"right",color:chartColor("text")}, barMaxWidth:22 }]
  });
}
function renderLianbanChart(tiers) {
  const el = $("lianbanChart");
  if (!lianbanChart) lianbanChart = echarts.init(el, chartTheme());
  const keys = Object.keys(tiers).map(Number).sort((a,b)=>a-b);
  const names = keys.map(k=>k+"板");
  const values = keys.map(k=>(tiers[k]||[]).length);
  lianbanChart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger:"axis", axisPointer:{type:"shadow"} },
    grid: { left: 50, right: 30, top: 30, bottom: 40 },
    xAxis: { type:"category", data:names, axisLabel:{color:"#d1d5db"}, axisLine:{lineStyle:{color:chartColor("line")}} },
    yAxis: { type:"value", axisLabel:{color:chartColor("axis")}, splitLine:{lineStyle:{color:chartColor("line")}} },
    series: [{ type:"bar", data:values, itemStyle:{color:"#f59e0b",borderRadius:[4,4,0,0]}, label:{show:true,position:"top",color:chartColor("text")}, barMaxWidth:48 }]
  });
}

window.addEventListener("resize", () => { themeChart && themeChart.resize(); lianbanChart && lianbanChart.resize(); });

// ---------- 连板梯队卡片渲染 ----------
function renderLianbanBoard(groups) {
    const box = $("lianbanBoard");
    if (!box) return;
    const badge = $("lianbanBadge");
    if (badge) {
        const total = groups.reduce((s, g) => s + (g.stocks ? g.stocks.length : 0), 0);
        badge.textContent = total;
    }
    if (!groups || !groups.length) {
        box.innerHTML = '<div style="color:#666;padding:12px;">暂无数据</div>';
        return;
    }
    box.innerHTML = groups.map(g => {
        const cards = (g.stocks || []).map(s => {
            const st = s.status || "";
            const stCls = st === "一字板" ? "yizi" : st === "未开板" ? "weikai" : "";
            return `<div class="lb-card" title="${s.code} ${s.name}">
                <div class="lb-head"><span>${s.time || ""}</span></div>
                <div><span class="lb-name">${s.name}</span><span class="lb-lb">${s.lb}板</span></div>
                <div class="lb-status ${stCls}">${st}</div>
                <div class="lb-theme-tag">${g.theme}</div>
            </div>`;
        }).join("");
        return `<div class="lb-row">
            <div class="lb-theme">
                <div class="lb-theme-name">${g.theme}</div>
                <div class="lb-theme-count">${g.count} 家</div>
            </div>
            <div class="lb-cards">${cards}</div>
        </div>`;
    }).join("");
}

// =====================================================
// 个股详情 Modal
// =====================================================
let mChart = null;
let mChartKind = "kline";
let mCurrentCode = null;
let mChartData = { minute: [], kline: [] };

function openStockModal(code, name) {
    if (!ENABLE_STOCK_MODAL) {
        console.log(`[Modal] 已禁用，忽略点击：${code} ${name}`);
        return;
    }
    mCurrentCode = code;
    $("mStockName").textContent = name || "-";
    $("mStockCode").textContent = code || "-";
    $("mPrice").textContent = "-";
    $("mPct").textContent = "-";
    $("mPct").className = "pct";
    $("mReason").textContent = "加载中...";
    $("mZtHistory").innerHTML = '<div style="color:#666;">加载中...</div>';
    $("mBidAsk").innerHTML = '<div class="k">加载中...</div>';
    $("stockModal").classList.remove("hidden");

    // 显示后初始化图表
    setTimeout(() => {
        if (!mChart) mChart = echarts.init($("mChart"), chartTheme());
        mChart.clear();
        mChart.resize();
    }, 30);

    fetch(`/api/stock/${code}?date=${currentDate || ""}`)
        .then(r => r.json())
        .then(j => {
            if (j.code !== 0) throw new Error(j.msg);
            renderStockDetail(j.data);
        })
        .catch(e => {
            alert("加载个股详情失败：" + e.message);
        });
}

function renderStockDetail(d) {
    mChartData.minute = d.minute || [];
    mChartData.kline = d.kline || [];

    // 顶部价格（优先用盘口的实时报价）
    const ba = d.bid_ask || {};
    if (ba["最新"] != null) {
        $("mPrice").textContent = ba["最新"];
        const pct = Number(ba["涨幅"] || 0);
        $("mPct").textContent = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
        $("mPct").className = "pct " + (pct > 0 ? "text-up" : pct < 0 ? "text-down" : "");
    } else if (mChartData.kline.length) {
        const last = mChartData.kline[mChartData.kline.length - 1];
        const price = last["close"];
        $("mPrice").textContent = price;
    }

    // 涨停原因
    $("mReason").textContent = d.reason || "无记录";

    // 涨停历史
    const hist = d.zt_history || [];
    $("mZtCount").textContent = hist.length + " 次";
    if (!hist.length) {
        $("mZtHistory").innerHTML = '<div style="color:#666;">近60个交易日无涨停</div>';
    } else {
        $("mZtHistory").innerHTML = hist.map(r => `
            <div class="zt-item">
                <span class="d">${r.date_fmt}</span>
                <span class="lb">${r.lb}板</span>
                <span class="ind">${r.industry || "-"}</span>
            </div>
        `).join("");
    }

    // 盘口
    renderBidAsk(d.bid_ask || {});

    // 画图
    if (!mChart) mChart = echarts.init($("mChart"), chartTheme());
    drawChart(mChartKind);
}

function renderBidAsk(ba) {
    const box = $("mBidAsk");
    const mainKeys = [
        ["最新", "最新"], ["涨幅", "涨幅"], ["涨跌", "涨跌"],
        ["今开", "今开"], ["昨收", "昨收"],
        ["最高", "最高"], ["最低", "最低"],
        ["换手率", "换手"], ["量比", "量比"], ["振幅", "振幅"],
        ["成交量手", "成交量"], ["成交额万", "成交额(万)"],
        ["流通市值亿", "流通市值(亿)"], ["总市值亿", "总市值(亿)"],
        ["涨停价", "涨停"], ["跌停价", "跌停"],
    ];
    const cells = [];
    mainKeys.forEach(([src, label]) => {
        const v = ba[src];
        if (v === undefined || v === null) return;
        let cls = "";
        if (src === "涨幅" || src === "涨跌") cls = v > 0 ? "up" : v < 0 ? "down" : "";
        cells.push(`<div><span class="k">${label}：</span><span class="v ${cls}">${v}</span></div>`);
    });
    // 五档
    for (let i = 1; i <= 5; i++) {
        const bp = ba[`买${i}价`], bv = ba[`买${i}量`];
        const sp = ba[`卖${i}价`], sv = ba[`卖${i}量`];
        if (bp != null) cells.push(`<div><span class="k">买${i}：</span><span class="v up">${bp} × ${bv||0}</span></div>`);
        if (sp != null) cells.push(`<div><span class="k">卖${i}：</span><span class="v down">${sp} × ${sv||0}</span></div>`);
    }
    box.innerHTML = cells.length ? cells.join("") : '<div class="k">无盘口数据</div>';
}

function drawChart(kind) {
    if (!mChart) return;
    mChart.clear();
    if (kind === "kline") {
        const kd = mChartData.kline;
        if (!kd.length) { mChart.setOption({ title:{text:"无K线数据", textStyle:{color:"#666"}, left:"center", top:"center"} }); return; }
        const dates = kd.map(r => r["date"] || r["日期"]);
        const ohlc = kd.map(r => [r["open"], r["close"], r["low"], r["high"]]);
        mChart.setOption({
            backgroundColor: "transparent",
            tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
            grid: { left: 50, right: 20, top: 20, bottom: 40 },
            xAxis: { type:"category", data:dates, axisLabel:{color:"#9ca3af",fontSize:10}, axisLine:{lineStyle:{color:chartColor("line")}} },
            yAxis: { scale:true, axisLabel:{color:chartColor("axis")}, splitLine:{lineStyle:{color:chartColor("line")}} },
            series: [{
                type: "candlestick",
                data: ohlc,
                itemStyle: {
                    color: "#ef4444", color0: "#22c55e",
                    borderColor: "#ef4444", borderColor0: "#22c55e"
                }
            }]
        });
    } else {
        const md = mChartData.minute;
        if (!md.length) { mChart.setOption({ title:{text:"无分时数据（可能非当日）", textStyle:{color:"#666"}, left:"center", top:"center"} }); return; }
        const times = md.map(r => r["time"] || "");
        const prices = md.map(r => r["price"]);
        mChart.setOption({
            backgroundColor: "transparent",
            tooltip: { trigger: "axis" },
            grid: { left: 50, right: 20, top: 20, bottom: 40 },
            xAxis: { type:"category", data:times, axisLabel:{color:"#9ca3af",fontSize:10}, axisLine:{lineStyle:{color:chartColor("line")}} },
            yAxis: { scale:true, axisLabel:{color:chartColor("axis")}, splitLine:{lineStyle:{color:chartColor("line")}} },
            series: [{
                type: "line", data: prices, smooth: true,
                lineStyle: { color: "#3b82f6", width: 1.5 },
                areaStyle: { color: "rgba(59,130,246,.15)" },
                symbol: "none"
            }]
        });
    }
    mChart.resize();
}

// 绑定 table 行点击
function bindRowClick() {
    ["ztTable","zbTable","dtTable"].forEach(tid => {
        const tbody = document.querySelector(`#${tid} tbody`);
        if (!tbody) return;
        if (tbody.dataset.bound === "1") return;
        tbody.dataset.bound = "1";
        tbody.addEventListener("click", (ev) => {
            const tr = ev.target.closest("tr");
            if (!tr) return;
            const tds = tr.querySelectorAll("td");
            if (tds.length < 2) return;
            const code = tds[0].textContent.trim();
            const name = tds[1].textContent.trim();
            if (code) openStockModal(code, name);
        });
    });
}

// 绑定卡片点击
function bindCardClick() {
    const board = $("lianbanBoard");
    if (!board || board.dataset.bound === "1") return;
    board.dataset.bound = "1";
    board.addEventListener("click", (ev) => {
        const card = ev.target.closest(".lb-card");
        if (!card) return;
        const code = card.dataset.code;
        const name = card.dataset.name;
        if (code) openStockModal(code, name);
    });
}

// 初始化 modal 事件
(function initModal() {
    const closeBtn = $("mClose");
    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            $("stockModal").classList.add("hidden");
        });
    }
    const overlay = $("stockModal");
    if (overlay) {
        overlay.addEventListener("click", (ev) => {
            if (ev.target === overlay) overlay.classList.add("hidden");
        });
    }
    document.querySelectorAll(".mini-tab").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".mini-tab").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            mChartKind = btn.dataset.k;
            drawChart(mChartKind);
        });
    });
    document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") {
            const m = $("stockModal");
            if (m && !m.classList.contains("hidden")) m.classList.add("hidden");
        }
    });
})();

// 覆盖 renderTable，渲染后自动重新绑定行点击
const _origRenderTable = renderTable;
renderTable = function(tid) {
    _origRenderTable(tid);
    bindRowClick();
};

// 覆盖 renderLianbanBoard，给卡片加 data-code/name
const _origRenderLianbanBoard = renderLianbanBoard;
renderLianbanBoard = function(groups) {
    _origRenderLianbanBoard(groups);
    // 给已渲染的卡片加 data 属性
    const cards = document.querySelectorAll("#lianbanBoard .lb-card");
    cards.forEach((card, i) => {
        // 由于 renderLianbanBoard 用 title 带了 code/name，解析出来
        const title = card.getAttribute("title") || "";
        const parts = title.split(" ");
        if (parts.length >= 2) {
            card.dataset.code = parts[0];
            card.dataset.name = parts.slice(1).join(" ");
        }
    });
    bindCardClick();
};

// =====================================================
// 龙虎榜面板
// =====================================================
let lhbData = { today: [], three_day: [], summary: {}, filtered: { today: [], three_day: [] } };
let lhbFilter = "all";
let lhbExpanded = new Set();

async function loadLhbPanel() {
    if (!currentDate) return;
    const list = $("lhbList");
    if (list) list.innerHTML = '<div style="color:#666;padding:20px;">加载中...</div>';
    try {
        const res = await fetch(`/api/lhb/${currentDate}`);
        const json = await res.json();
        if (json.code !== 0) throw new Error(json.msg);
        const d = json.data || {};
        lhbData.today = d.today_stocks || [];
        lhbData.three_day = d.three_day_stocks || [];
        lhbData.summary = d.summary || {};
        lhbExpanded.clear();

        const cnt = $("cntLhb");
        if (cnt) {
            const codes = new Set([...lhbData.today, ...lhbData.three_day].map(s => s.code));
            cnt.textContent = codes.size;
        }
        renderLhbSummary();
        applyLhbFilter();
    } catch (e) {
        if (list) list.innerHTML = `<div style="color:#ef4444;padding:20px;">加载失败：${e.message}</div>`;
    }
}

function renderLhbSummary() {
    const s = lhbData.summary || {};
    const el = $("lhbSummary");
    if (!el) return;
    const net = s.total_net_buy || 0;
    const netCls = net > 0 ? "text-up" : net < 0 ? "text-down" : "";
    const top3 = (s.top3 || []).join(" · ") || "-";
    el.innerHTML = `
        <div class="lhb-sum-item">上榜 <b>${s.total_stocks || 0}</b> 只（${s.total_lhb || 0} 条榜单）</div>
        <div class="lhb-sum-item">合计净买 <b class="${netCls}">${fmtMoney2(net)}</b></div>
        <div class="lhb-sum-item">机构参与 <b>${s.institution_count || 0}</b> 只</div>
        <div class="lhb-sum-item">净买Top3 <b>${top3}</b></div>
    `;
}

function _filterStocks(arr) {
    const f = lhbFilter;
    if (f === "net-buy")     return arr.filter(s => s.net_buy > 0);
    if (f === "net-sell")    return arr.filter(s => s.net_buy < 0);
    if (f === "institution") return arr.filter(s => (s.tags || []).includes("机构"));
    if (f === "hotmoney")    return arr.filter(s => (s.tags || []).includes("游资"));
    return arr;
}

function applyLhbFilter() {
    lhbData.filtered.today = _filterStocks(lhbData.today.slice());
    lhbData.filtered.three_day = _filterStocks(lhbData.three_day.slice());
    renderLhbList();
}

function _renderLhbGroup(title, groupKey, arr) {
    if (!arr.length) {
        return `<div class="lhb-group">
            <div class="lhb-group-title">${title} <span class="count">0</span></div>
            <div style="color:#666;padding:12px;text-align:center;">无数据</div>
        </div>`;
    }
    const items = arr.map(s => {
        const pctCls = s.pct_chg > 0 ? "text-up" : s.pct_chg < 0 ? "text-down" : "";
        const netCls = s.net_buy > 0 ? "text-up" : s.net_buy < 0 ? "text-down" : "";
        const tags = (s.tags || []).map(t =>
            `<span class="lhb-tag ${t === "机构" ? "inst" : "hot"}">${t}</span>`
        ).join("");
        const expKey = groupKey + "_" + s.code;
        const isExp = lhbExpanded.has(expKey);
        return `
        <div class="lhb-item-wrap" data-code="${s.code}" data-group="${groupKey}" data-key="${expKey}">
            <div class="lhb-item">
                <span class="stock-name">${s.name || ""}</span>
                <span class="stock-code">${s.code || ""}</span>
                <span class="pct ${pctCls}">${s.pct_chg > 0 ? "+" : ""}${Number(s.pct_chg).toFixed(1)}%</span>
                <span class="net-buy ${netCls}">净 ${fmtMoney2(s.net_buy)}</span>
                <span class="tags">${tags}</span>
                <span class="reason" title="${(s.reason||"").replace(/"/g,"&quot;")}">${s.reason || ""}</span>
                <button class="expand-btn">${isExp ? "收起" : "展开"}</button>
            </div>
            <div class="lhb-detail ${isExp ? "show" : ""}"></div>
        </div>`;
    }).join("");
    const groupNet = arr.reduce((s, x) => s + (x.net_buy || 0), 0);
    const netCls = groupNet > 0 ? "text-up" : groupNet < 0 ? "text-down" : "";
    return `<div class="lhb-group">
        <div class="lhb-group-title">${title} <span class="count">${arr.length}</span>
            <span style="margin-left:12px;font-size:12px;color:#9ca3af;">净买合计
                <b class="${netCls}" style="font-size:13px;">${fmtMoney2(groupNet)}</b>
            </span>
        </div>
        <div class="lhb-items">${items}</div>
    </div>`;
}

function renderLhbList() {
    const list = $("lhbList");
    if (!list) return;
    const today = lhbData.filtered.today || [];
    const three = lhbData.filtered.three_day || [];
    if (!today.length && !three.length) {
        list.innerHTML = '<div style="color:#666;padding:20px;text-align:center;">无数据</div>';
        return;
    }
    list.innerHTML = _renderLhbGroup("📅 当日榜", "today", today)
                   + _renderLhbGroup("📊 三日榜", "three", three);

    // 绑定事件
    list.querySelectorAll(".expand-btn").forEach(btn => {
        btn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            const wrap = ev.target.closest(".lhb-item-wrap");
            toggleLhbDetail(wrap);
        });
    });
    list.querySelectorAll(".lhb-item").forEach(item => {
        item.addEventListener("click", (ev) => {
            if (ev.target.classList.contains("expand-btn")) return;
            const wrap = item.closest(".lhb-item-wrap");
            const code = wrap.dataset.code;
            const name = wrap.querySelector(".stock-name").textContent;
            if (typeof openStockModal === "function") openStockModal(code, name);
        });
    });
}

async function toggleLhbDetail(wrap) {
    const code = wrap.dataset.code;
    const key = wrap.dataset.key || code;
    const group = wrap.dataset.group || "today";
    const detail = wrap.querySelector(".lhb-detail");
    const btn = wrap.querySelector(".expand-btn");

    if (lhbExpanded.has(key)) {
        lhbExpanded.delete(key);
        detail.classList.remove("show");
        btn.textContent = "展开";
        return;
    }
    lhbExpanded.add(key);
    detail.classList.add("show");
    btn.textContent = "收起";

    if (detail.dataset.loaded === "1") {
        // 已加载过，标签已经打过，无需重复请求
        return;
    }
    detail.innerHTML = '<div style="color:#666;">加载中...</div>';

    try {
        const res = await fetch(`/api/lhb_detail/${code}?date=${currentDate || ""}`);
        const json = await res.json();
        if (json.code !== 0) throw new Error(json.msg);
        detail.innerHTML = renderLhbDetailHTML(json.data);
        detail.dataset.loaded = "1";

        // ★ 关键：按营业部名称匹配 YZ_MAP，命中才贴游资标签
        checkYouziTag(code, group, json.data);
    } catch (e) {
        detail.innerHTML = `<div style="color:#ef4444;">加载失败：${e.message}</div>`;
    }
}

// 检查营业部是否命中游资名单，命中则给该行追加游资标签
function checkYouziTag(code, group, detailData) {
    const yybNames = [];
    (detailData.buy || []).forEach(r => r.yyb && yybNames.push(r.yyb));
    (detailData.sell || []).forEach(r => r.yyb && yybNames.push(r.yyb));

    const hits = new Set();
    yybNames.forEach(name => {
        const yz = findYouzi(name);
        if (yz) hits.add(yz);
    });

    if (!hits.size) return;   // 没命中，什么都不做

    // 1) 写回数据对象，切换筛选后仍保留
    const arr = group === "three" ? lhbData.three_day : lhbData.today;
    const stock = arr.find(s => s.code === code);
    if (stock) {
        stock.tags = stock.tags || [];
        if (!stock.tags.includes("游资")) stock.tags.push("游资");
        stock.youzi_names = stock.youzi_names || [];
        hits.forEach(n => {
            if (!stock.youzi_names.includes(n)) stock.youzi_names.push(n);
        });
    }

    // 2) 更新该行 DOM 的标签区
    const key = group + "_" + code;
    const wrap = document.querySelector(`.lhb-item-wrap[data-key="${key}"]`);
    if (!wrap) return;
    const tagsEl = wrap.querySelector(".tags");
    if (!tagsEl) return;

    const hasHot = Array.from(tagsEl.querySelectorAll(".lhb-tag"))
        .some(el => el.textContent === "游资");
    if (!hasHot) {
        tagsEl.insertAdjacentHTML("beforeend",
            '<span class="lhb-tag hot">游资</span>');
    }

    hits.forEach(n => {
        const exists = Array.from(tagsEl.querySelectorAll(".lhb-tag"))
            .some(el => el.textContent === n);
        if (!exists) {
            tagsEl.insertAdjacentHTML("beforeend",
                `<span class="lhb-tag youzi-name" title="命中游资：${n}">${n}</span>`);
        }
    });
}

// 知名游资 → 常用营业部关键词映射（子串匹配，命中即标注）
const YZ_MAP = [
    // ========== 顶级游资 ==========
    ["章盟主",     ["国泰海通上海江苏路", "国泰君安上海江苏路", "国泰海通上海海阳西路",
                    "国泰海通上海徐汇建国西路", "国泰海通宁波彩虹北路", "中信杭州延安路",
                    "中信杭州富春路", "浙商杭州五星路", "银泰上海嘉善路", "银泰上海延安西路"]],
    ["赵老哥",     ["银河绍兴", "中国银河证券绍兴", "浙商绍兴分公司", "银河北京阜成路",
                    "华泰浙江分公司", "中信杭州庆春路", "银泰上海长宁延安西路"]],
    ["孙哥",       ["中信上海溧阳路", "中信上海淮海中路", "中信上海古北路",
                    "中信上海分公司", "光大杭州庆春路", "中信上海瑞金南路"]],
    ["葛老大",     ["国泰海通上海分公司", "华泰上海共和新路", "中信上海浦东大道"]],
    // ========== 一线游资 ==========
    ["炒股养家",   ["华鑫上海宛平南路", "华鑫上海茅台路", "华鑫上海红宝石路",
                    "华鑫上海分公司", "华鑫宁波分公司"]],
    ["方新侠",     ["中信证券西安朱雀大街", "国投证券西安曲江池南路", "兴业证券陕西分公司"]],
    ["作手新一",   ["国泰海通证券南京太平南路", "国泰君安南京太平南路"]],
    ["小鳄鱼",     ["东方证券上海浦东新区源深路", "中金财富证券南京太平南路",
                    "南京证券南京大钟亭", "长江证券上海世纪大道"]],
    ["陈小群",     ["银河证券大连黄河路"]],
    ["欢乐海岸",   ["中信证券深圳分公司", "广发证券深圳民田路",
                    "中天证券深圳民田路", "中信证券深圳后海"]],
    ["量化打板",   ["开源证券西安西大街"]],
    ["中山东路",   ["国泰海通证券上海松江区中山东路", "国泰海通证券上海松江中山东"]],
    ["北京光华路", ["国泰海通证券北京国贸"]],
    // ========== 区域派系 ==========
    ["成都帮",     ["国泰海通成都北一环路", "国泰君安成都北一环路", "中信证券临淄分公司",
                    "华泰证券成都南一环路", "华泰证券德阳中江县", "中信建投证券成都马家花园"]],
    ["佛山系",     ["光大证券佛山绿景路", "光大证券佛山季华六路", "新时代证券佛山南海大道",
                    "华泰证券广州天河东路", "湘财证券佛山祖庙路", "长江证券佛山普澜二路"]],
    ["杭州帮",     ["西南证券杭州庆春东路", "光大证券杭州庆春路", "光大证券杭州延安路",
                    "银河证券杭州天城东路", "银河杭州凤起路", "银河证券杭州新塘路",
                    "银河证券杭州庆春路", "中信建投证券杭州庆春路", "中信证券杭州庆春路"]],
    ["绍兴帮",     ["银河证券绍兴", "中国银河证券绍兴"]],
    ["深圳帮",     ["华泰证券深圳益田路", "国信证券深圳泰然九路"]],
    ["上海帮",     ["华泰证券上海武定路"]],
    ["北京帮",     ["中信建投北京朝外大街"]],
    // ========== 其他知名席位 ==========
    ["消闲派",     ["国泰海通证券宜昌沿江大道"]],
    ["徐晓",       ["国元证券上海虹桥路"]],
    ["桑田路",     ["国盛证券宁波桑田路"]],
    ["著名刺客",   ["华福证券泉州分公司", "东莞证券北京分公司", "海通证券北京阜外大街"]],
    ["苏南帮",     ["银河证券北京学院南路"]],
];

function findYouzi(yybName) {
    if (!yybName) return null;
    for (const [name, kws] of YZ_MAP) {
        for (const kw of kws) {
            if (yybName.includes(kw)) return name;
        }
    }
    return null;
}

function renderLhbDetailHTML(d) {
    const buy = d.buy || [], sell = d.sell || [];
    const mkRow = (r) => {
        const yyb = (r.yyb || "-").trim();
        const yz = findYouzi(yyb);
        const esc = yyb.replace(/"/g, "&quot;");
        const nameHtml = yz
            ? `<span class="youzi-tag">${yz}</span><span class="youzi-dot">·</span><span class="yyb-name">${yyb}</span>`
            : `<span class="yyb-name">${yyb}</span>`;
        return `
        <div class="lhb-yyb-row">
            <span class="name" title="${esc}">${nameHtml}</span>
            <span class="amt buy">买 ${fmtMoney2(r.buy)}</span>
            <span class="amt sell">卖 ${fmtMoney2(r.sell)}</span>
        </div>`;
    };
    return `
        <div class="lhb-detail-grid">
            <div>
                <h5>买入前5</h5>
                ${buy.length ? buy.map(mkRow).join("") : '<div style="color:#666;">无数据</div>'}
            </div>
            <div>
                <h5>卖出前5</h5>
                ${sell.length ? sell.map(mkRow).join("") : '<div style="color:#666;">无数据</div>'}
            </div>
        </div>`;
}

function fmtMoney2(v) {
    if (v == null || isNaN(v)) return "-";
    const n = Number(v);
    const sign = n < 0 ? "-" : "";
    const a = Math.abs(n);
    if (a >= 1e8) return sign + (a / 1e8).toFixed(2) + "亿";
    if (a >= 1e4) return sign + Math.round(a / 1e4) + "万";
    return sign + Math.round(a);
}

// 过滤标签点击
(function initLhbFilters() {
    document.querySelectorAll(".lhb-filter").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".lhb-filter").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            lhbFilter = btn.dataset.filter;
            applyLhbFilter();
        });
    });
})();

// =====================================================
// 游资席位面板
// =====================================================
function renderYouziPanel() {
    const list = $("youziList");
    if (!list) return;

    if (typeof YZ_MAP === "undefined" || !YZ_MAP.length) {
        list.innerHTML = '<div class="youzi-empty">未加载到游资数据</div>';
        return;
    }

    // 统计
    let totalYyb = 0;
    YZ_MAP.forEach(([_, kws]) => { totalYyb += (kws || []).length; });
    const c1 = $("youziCount"); if (c1) c1.textContent = YZ_MAP.length;
    const c2 = $("yybCount");   if (c2) c2.textContent = totalYyb;

    const kw = ($("youziSearch")?.value || "").trim().toLowerCase();

    const html = YZ_MAP.map(([name, kws]) => {
        const yybList = (kws || []).filter(k => !kw || k.toLowerCase().includes(kw) || name.toLowerCase().includes(kw));
        if (kw && yybList.length === 0) return "";
        return `
        <div class="youzi-item" data-name="${name}">
            <div class="youzi-name-box">
                <span class="youzi-name-tag">${name}</span>
                <span class="youzi-count">${(kws || []).length} 个席位</span>
            </div>
            <div class="youzi-yyb-list">
                ${(kws || []).map(k => `<span class="youzi-yyb">${k}</span>`).join("")}
            </div>
        </div>`;
    }).filter(Boolean).join("");

    list.innerHTML = html || '<div class="youzi-empty">没有匹配的游资</div>';
}

// 首次进入"游资席位"标签时渲染
(function initYouziTab() {
    const tab = document.querySelector('.tab[data-tab="youzi"]');
    if (tab) {
        tab.addEventListener("click", () => {
            setTimeout(renderYouziPanel, 10);
        });
        console.log("[YOUZI] 游资席位 tab 事件已绑定");
    } else {
        console.warn("[YOUZI] 未找到 tab[data-tab=youzi]");
    }
    const search = document.getElementById("youziSearch");
    if (search) {
        search.addEventListener("input", renderYouziPanel);
    }
})();

// =====================================================
// 游资追踪面板
// =====================================================
let yzTraceLoaded = {};

async function loadYouziTrace(forceRefresh) {
    console.log("[YOUZI] loadYouziTrace 被调用, forceRefresh=" + !!forceRefresh + ", currentDate=" + currentDate);
    const box = $("youziTraceList");
    if (!box) {
        console.warn("[YOUZI] 未找到 #youziTraceList 元素");
        return;
    }
    // 兜底：如果没查询过，用日期选择框当前值
    if (!currentDate) {
        const raw = document.getElementById("dateInput")?.value || "";
        if (raw) {
            currentDate = raw.replace(/-/g, "");
            console.log("[YOUZI] currentDate 为空，从 dateInput 读取: " + currentDate);
        } else {
            console.warn("[YOUZI] currentDate 为空且 dateInput 无值");
            box.innerHTML = '<div style="color:#f59e0b;padding:20px;">请先在上方选择日期并点击「查询」</div>';
            return;
        }
    }

    if (!forceRefresh && yzTraceLoaded[currentDate]) {
        console.log("[YOUZI] 命中前端缓存，跳过请求");
        return;
    }

    box.innerHTML = '<div style="color:#666;padding:20px;">正在聚合，首次需要 30-90 秒...</div>';
    try {
        const url = `/api/youzi_trace/${currentDate}${forceRefresh ? "?refresh=1" : ""}`;
        const res = await fetch(url);
        const json = await res.json();
        if (json.code !== 0) throw new Error(json.msg);
        renderYouziTrace(json.data);
        yzTraceLoaded[currentDate] = true;
    } catch (e) {
        box.innerHTML = `<div style="color:#ef4444;padding:20px;">加载失败：${e.message}</div>`;
    }
}

function renderYouziTrace(data) {
    console.log("[YOUZI] 渲染", (data.youzi || []).length, "个游资");
    const box = $("youziTraceList");
    if (!box) return;
    const arr = data.youzi || [];
    if (!arr.length) {
        box.innerHTML = '<div style="color:#666;padding:20px;text-align:center;">当日无游资上榜</div>';
        return;
    }

    box.innerHTML = arr.map(y => {
        const bothBadge = (y.buys.length && y.sells.length)
            ? '<span class="yz-badge both">双向</span>' : "";

        const buyLine = y.buys.length ? `
            <div class="yz-trace-row">
                <span class="yz-action buy">买</span>
                ${y.buys.map(s => `
                    <span class="yz-stock" data-code="${s.code}" data-name="${s.name}" title="${s.name} ${s.code}">
                        <span class="code">${s.code}</span>
                        <span class="name">${s.name}</span>
                        <span class="amt">${fmtMoney2(s.amount)}</span>
                    </span>
                `).join("")}
            </div>` : "";

        const sellLine = y.sells.length ? `
            <div class="yz-trace-row">
                <span class="yz-action sell">卖</span>
                ${y.sells.map(s => `
                    <span class="yz-stock" data-code="${s.code}" data-name="${s.name}" title="${s.name} ${s.code}">
                        <span class="code">${s.code}</span>
                        <span class="name">${s.name}</span>
                        <span class="amt">${fmtMoney2(s.amount)}</span>
                    </span>
                `).join("")}
            </div>` : "";

        const totalBuy = y.buy_total > 0 ? `买 ${fmtMoney2(y.buy_total)}` : "";
        const totalSell = y.sell_total > 0 ? `卖 ${fmtMoney2(y.sell_total)}` : "";
        const totalLine = [totalBuy, totalSell].filter(Boolean).join(" / ");
        const countLine = `${y.buy_count + y.sell_count} 笔`;

        return `
        <div class="yz-trace-item">
            <div class="yz-trace-head">
                <div class="yz-trace-name">
                    <span class="youzi-name-tag">${y.name}</span>
                    ${bothBadge}
                </div>
                <div class="yz-trace-total">${totalLine} · ${countLine}</div>
            </div>
            ${buyLine}
            ${sellLine}
        </div>`;
    }).join("");

    // 绑定点击
    box.querySelectorAll(".yz-stock").forEach(el => {
        el.addEventListener("click", () => {
            if (typeof openStockModal === "function") {
                openStockModal(el.dataset.code, el.dataset.name);
            }
        });
    });
}

// 标签点击时懒加载（脚本在 body 末尾，DOM 已就绪，无需等 DOMContentLoaded）
(function initYouziTraceTab() {
    const tab = document.querySelector('.tab[data-tab="youziTrace"]');
    if (tab) {
        tab.addEventListener("click", () => loadYouziTrace(false));
        console.log("[YOUZI] 游资追踪 tab 事件已绑定");
    } else {
        console.warn("[YOUZI] 未找到 tab[data-tab=youziTrace]");
    }
    const refreshBtn = document.getElementById("yzTraceRefresh");
    if (refreshBtn) refreshBtn.addEventListener("click", () => loadYouziTrace(true));
})();

// =====================================================
// 情绪监控面板
// =====================================================
function renderSentiment(s) {
    if (!s || s.score == null) return;
    const scoreEl = $("sentScore");
    const levelEl = $("sentLevel");
    const barEl = $("sentBarFill");
    const gridEl = $("sentGrid");
    if (!scoreEl || !levelEl || !barEl || !gridEl) return;

    const cls = s.level_cls || "neutral";
    scoreEl.textContent = s.score;
    scoreEl.className = "sent-score " + cls;
    levelEl.textContent = s.level || "-";
    levelEl.className = "sent-level " + cls;
    barEl.style.width = Math.min(100, Math.max(0, s.score)) + "%";
    barEl.className = "sent-bar-fill " + cls;

    const statusText = { good: "强", mid: "中", bad: "弱" };
    gridEl.innerHTML = (s.items || []).map(it => `
        <div class="sent-item ${it.status}" title="${it.hint || ""}">
            <div class="sent-item-head">
                <span class="sent-item-label">${it.label}</span>
                <span class="sent-item-status">${statusText[it.status] || ""}</span>
            </div>
            <div class="sent-item-value">${it.value}</div>
            <div class="sent-item-hint">${it.hint || ""}</div>
        </div>
    `).join("");
}

// =====================================================
// 板块资金流向面板
// =====================================================
function fmtFlow(v) {
    if (v == null || isNaN(v)) return "-";
    const n = Number(v);
    const sign = n > 0 ? "+" : n < 0 ? "-" : "";
    const a = Math.abs(n);
    if (a >= 1e8) return sign + (a / 1e8).toFixed(2) + "亿";
    if (a >= 1e4) return sign + Math.round(a / 1e4) + "万";
    return sign + Math.round(a);
}

function sfSignalClass(sig) {
    if (sig === "加速流入")   return "accel-in";
    if (sig === "持续流入")   return "cont-in";
    if (sig === "加速流出")   return "accel-out";
    if (sig === "持续流出")   return "cont-out";
    if (sig === "由流出转流入") return "turn-in";
    if (sig === "由流入转流出") return "turn-out";
    return "";
}

function renderSectorFlow(sf) {
    console.log("[SF] renderSectorFlow 被调用, 数据:", sf);
    console.log("[SF] inflow 条数:", (sf.inflow || []).length);
    console.log("[SF] outflow 条数:", (sf.outflow || []).length);
    const inEl = $("sfInflow");
    const outEl = $("sfOutflow");
    const rotEl = $("sfRotation");
    if (!inEl || !outEl || !rotEl) return;

    const mkItem = (r) => {
        const netCls = r.main_net > 0 ? "up" : "down";
        const sigCls = sfSignalClass(r.signal);
        const sigHtml = r.signal
            ? `<span class="sf-signal ${sigCls}">${r.signal}</span>` : "";
        return `
        <div class="sf-item" title="${r.leader ? "领涨：" + r.leader : ""}">
            <span class="sf-name">${r.sector}${sigHtml}</span>
            <span class="sf-flow ${netCls}">${fmtFlow(r.main_net)}</span>
            <span class="sf-flow5d" title="3日/5日/10日累计">3d ${fmtFlow(r.main_net_3d)} · 5d ${fmtFlow(r.main_net_5d)} · 10d ${fmtFlow(r.main_net_10d)}</span>
        </div>`;
    };

    inEl.innerHTML = (sf.inflow || []).length
        ? sf.inflow.map(mkItem).join("")
        : '<div style="color:#666;padding:10px;">无数据</div>';
    outEl.innerHTML = (sf.outflow || []).length
        ? sf.outflow.map(mkItem).join("")
        : '<div style="color:#666;padding:10px;">无数据</div>';

    // 轮动摘要
    const rot = sf.rotation_signal || {};
    const inList = (rot.in || []).join("、") || "-";
    const outList = (rot.out || []).join("、") || "-";
    if (inList === "-" && outList === "-") {
        rotEl.style.display = "none";
    } else {
        rotEl.style.display = "block";
        rotEl.innerHTML = `
            🔄 资金流向：
            <b class="from">${outList}</b>
            <span class="sf-arrow">→</span>
            <b class="to">${inList}</b>
        `;
    }
}

// =====================================================
// 板块资金流：行业/概念切换 + 点击展开 + 趋势
// =====================================================
let sfType = "industry";
let sfDataCache = { industry: null, concept: null };

function initSectorTabs() {
    document.querySelectorAll(".sf-tab").forEach(btn => {
        btn.addEventListener("click", async () => {
            document.querySelectorAll(".sf-tab").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            sfType = btn.dataset.sfType;
            if (sfDataCache[sfType]) {
                renderSectorFlow(sfDataCache[sfType]);
            } else if (sfType === "concept") {
                await loadConceptFlow();
            }
        });
    });
}

async function loadConceptFlow() {
    if (!currentDate) return;
    try {
        const res = await fetch(`/api/concept_flow/${currentDate}`);
        const j = await res.json();
        if (j.code === 0) {
            sfDataCache.concept = j.data;
            renderSectorFlow(j.data);
        }
    } catch (e) {
        console.error("概念板块加载失败", e);
    }
}

// 覆盖 renderSectorFlow：加趋势按钮 + 点击展开
const _origRenderSectorFlow = renderSectorFlow;
renderSectorFlow = function(sf) {
    if (sfType === "industry") sfDataCache.industry = sf;
    const inEl = $("sfInflow");
    const outEl = $("sfOutflow");
    const rotEl = $("sfRotation");
    if (!inEl || !outEl || !rotEl) return;

    const mkItem = (r) => {
        const netCls = r.main_net > 0 ? "up" : "down";
        const sigCls = sfSignalClass(r.signal);
        const sigHtml = r.signal ? `<span class="sf-signal ${sigCls}">${r.signal}</span>` : "";
        const flow5d = r.main_net_5d != null
            ? `<span class="sf-flow5d" title="5日累计">5d ${fmtFlow(r.main_net_5d)}</span>`
            : "";
        return `
        <div class="sf-item" data-sector="${r.sector}" title="点击查看成分股">
            <span class="sf-name">${r.sector}${sigHtml}</span>
            <span class="sf-flow ${netCls}">${fmtFlow(r.main_net)}</span>
            ${flow5d}
            <span class="sf-trend-btn" title="查看30日趋势">📈</span>
        </div>`;
    };

    inEl.innerHTML = (sf.inflow || []).length ? sf.inflow.map(mkItem).join("") : '<div style="color:#666;padding:10px;">无数据</div>';
    outEl.innerHTML = (sf.outflow || []).length ? sf.outflow.map(mkItem).join("") : '<div style="color:#666;padding:10px;">无数据</div>';

    // 事件
    document.querySelectorAll(".sf-item").forEach(el => {
        el.addEventListener("click", (ev) => {
            const sector = el.dataset.sector;
            if (ev.target.classList.contains("sf-trend-btn")) {
                openSectorModal(sector, "trend");
            } else {
                openSectorModal(sector, "stocks");
            }
        });
    });

    const rot = sf.rotation_signal || {};
    const inList = (rot.in || []).join("、") || "-";
    const outList = (rot.out || []).join("、") || "-";
    if (inList === "-" && outList === "-") {
        rotEl.style.display = "none";
    } else {
        rotEl.style.display = "block";
        rotEl.innerHTML = `🔄 资金流向：<b class="from">${outList}</b><span class="sf-arrow">→</span><b class="to">${inList}</b>`;
    }
};

// 板块 Modal
let secChart = null;
let secCurrentTab = "stocks";
let secCurrentSector = null;

function openSectorModal(sectorName, tab) {
    secCurrentSector = sectorName;
    secCurrentTab = tab || "stocks";
    $("secModalTitle").textContent = sectorName;
    $("sectorModal").classList.remove("hidden");
    document.querySelectorAll(".modal-tabs .mini-tab").forEach(b => {
        b.classList.toggle("active", b.dataset.secTab === secCurrentTab);
    });
    switchSecTab(secCurrentTab);
}

async function switchSecTab(tab) {
    secCurrentTab = tab;
    $("secStocksPanel").style.display = tab === "stocks" ? "block" : "none";
    $("secTrendPanel").style.display = tab === "trend" ? "block" : "none";
    if (tab === "stocks") await loadSectorStocks();
    else await loadSectorTrend();
}

async function loadSectorStocks() {
    const tbody = document.querySelector("#secStockTable tbody");
    tbody.innerHTML = '<tr><td colspan="6" style="color:#666;">加载中...</td></tr>';
    try {
        const res = await fetch(`/api/sector_stocks/${encodeURIComponent(secCurrentSector)}?type=${sfType}`);
        const j = await res.json();
        if (j.code !== 0) throw new Error(j.msg);
        const arr = j.data || [];
        if (!arr.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="color:#666;">无数据</td></tr>';
            return;
        }
        tbody.innerHTML = arr.map(r => {
            const cls = r.pct_chg > 0 ? "text-up" : r.pct_chg < 0 ? "text-down" : "";
            return `<tr>
                <td>${r.code}</td>
                <td>${r.name}</td>
                <td class="${cls}">${r.pct_chg > 0 ? "+" : ""}${r.pct_chg.toFixed(2)}%</td>
                <td>${r.price.toFixed(2)}</td>
                <td>${r.turnover.toFixed(2)}%</td>
                <td>${fmtFlow(r.amount)}</td>
            </tr>`;
        }).join("");
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" style="color:#ef4444;">${e.message}</td></tr>`;
    }
}

async function loadSectorTrend() {
    if (!secChart) secChart = echarts.init($("secTrendChart"), chartTheme());
    secChart.showLoading();
    try {
        const res = await fetch(`/api/sector_trend/${encodeURIComponent(secCurrentSector)}?days=30`);
        const j = await res.json();
        if (j.code !== 0) throw new Error(j.msg);
        const arr = j.data || [];
        secChart.hideLoading();
        if (!arr.length) {
            secChart.setOption({ title: { text: "暂无历史数据（需累积）", left: "center", top: "middle", textStyle: { color: "#666" } } });
            return;
        }
        const dates = arr.map(x => x.date.slice(4, 6) + "-" + x.date.slice(6, 8));
        const vals = arr.map(x => (x.net / 1e8).toFixed(2));
        secChart.setOption({
            backgroundColor: "transparent",
            tooltip: { trigger: "axis" },
            grid: { left: 60, right: 20, top: 30, bottom: 40 },
            xAxis: { type: "category", data: dates, axisLabel: { color: chartColor("axis") } },
            yAxis: { type: "value", name: "亿元", axisLabel: { color: chartColor("axis") }, splitLine: { lineStyle: { color: chartColor("line") } } },
            series: [{
                type: "line", data: vals, smooth: true,
                areaStyle: { color: "rgba(59,130,246,.2)" },
                lineStyle: { color: "#3b82f6", width: 2 },
                itemStyle: { color: "#3b82f6" }
            }]
        });
    } catch (e) {
        secChart.hideLoading();
        alert("趋势加载失败：" + e.message);
    }
}

// 北向资金
async function loadNorthFlow() {
    try {
        const res = await fetch("/api/north_flow");
        const j = await res.json();
        if (j.code !== 0) return;
        const d = j.data || {};
        const total = d.total_net || 0;
        const totalEl = $("northTotal");
        if (!totalEl) return;
        totalEl.textContent = (total > 0 ? "+" : "") + (total / 1e8).toFixed(2) + " 亿";
        totalEl.className = "north-total " + (total > 0 ? "up" : total < 0 ? "down" : "");
        const itemsEl = $("northItems");
        if (itemsEl && d.items) {
            itemsEl.innerHTML = d.items.map(it => {
                const cls = it.net > 0 ? "up" : it.net < 0 ? "down" : "";
                return `<div class="north-item">${it.board || it.type} <b class="${cls}">${(it.net/1e8).toFixed(2)}亿</b></div>`;
            }).join("");
        }
    } catch (e) {
        console.error("北向资金加载失败", e);
    }
}

// 初始化
document.addEventListener("DOMContentLoaded", () => {
    initSectorTabs();
    const secClose = $("secClose");
    if (secClose) secClose.addEventListener("click", () => $("sectorModal").classList.add("hidden"));
    const secModal = $("sectorModal");
    if (secModal) secModal.addEventListener("click", (ev) => {
        if (ev.target === secModal) secModal.classList.add("hidden");
    });
    document.querySelectorAll(".modal-tabs .mini-tab").forEach(b => {
        b.addEventListener("click", () => {
            document.querySelectorAll(".modal-tabs .mini-tab").forEach(x => x.classList.remove("active"));
            b.classList.add("active");
            switchSecTab(b.dataset.secTab);
        });
    });
});
