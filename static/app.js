console.log("Anime Graph Explorer: app.js loaded v1.1");

let cy = null;
let currentCenterName = "";
let currentGraph = null;
let lastChatReqId = 0;

function $(id) {
  return document.getElementById(id);
}

function setTab(tab) {
  // Simple scrolling to sections on mobile if needed, or highlighting
  const btnGraph = $("tabGraphBtn");
  const btnChat = $("tabChatBtn");
  const btnDetail = $("tabDetailBtn");

  [btnGraph, btnChat, btnDetail].forEach(b => {
    b.className = "px-5 py-2.5 rounded-xl bg-transparent hover:bg-white/5 text-slate-300 text-sm font-bold transition-all";
  });

  if (tab === 'graph') {
    btnGraph.className = "px-5 py-2.5 rounded-xl bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 text-sm font-bold transition-all";
    $("tabGraph").scrollIntoView({ behavior: 'smooth' });
  } else if (tab === 'chat') {
    btnChat.className = "px-5 py-2.5 rounded-xl bg-purple-500 text-white shadow-lg shadow-purple-500/25 text-sm font-bold transition-all";
    $("tabChat").scrollIntoView({ behavior: 'smooth' });
  } else if (tab === 'detail') {
    btnDetail.className = "px-5 py-2.5 rounded-xl bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 text-sm font-bold transition-all";
    $("tabDetail").scrollIntoView({ behavior: 'smooth' });
  }
}

function setSmartTab(tab) {
  const tabs = ["search", "recommend", "casting", "character", "studio", "discover"];
  tabs.forEach((t) => {
    const panel = $(`tab-${t}`);
    if (!panel) return;
    if (t === tab) panel.classList.remove("hidden");
    else panel.classList.add("hidden");
  });

  const tabBtn = (name) => $(`tabBtn-${name}`);
  tabs.forEach((t) => {
    const btn = tabBtn(t);
    if (!btn) return;
    if (t === tab) {
      btn.className = "px-3 py-1.5 rounded-lg bg-indigo-500/20 border border-indigo-500/30 text-xs font-bold text-indigo-200 transition-all";
    } else {
      btn.className = "px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs font-bold text-slate-400 transition-all";
    }
  });
}

function clearSmartTab(tab) {
  if (tab === 'search') {
    $("searchInput").value = "";
    $("resultsBody").innerHTML = "运行上方功能即可在此查看结果...";
  } else if (tab === 'recommend') {
    $("recommendId").value = "";
  } else if (tab === 'casting') {
    $("castingTags").value = "";
  } else if (tab === 'character') {
    $("characterName").value = "";
  } else if (tab === 'studio') {
    $("studioName").value = "";
  } else if (tab === 'discover') {
    $("discoverRank").value = "";
    $("discoverTagCount").value = "";
  }
  
  if (tab !== 'search') {
    $("resultsBody").innerHTML = "运行上方功能即可在此查看结果...";
  }
  if ($("detailBody")) $("detailBody").innerHTML = "<div class='text-sm text-slate-400 italic'>点击图谱中的节点即可在此查看详细信息...</div>";
  clearHighlight();
}

function getEdgeFilters() {
  const checks = document.querySelectorAll("[data-edge-filter]");
  const types = new Set();
  checks.forEach((c) => {
    if (c.checked) types.add(c.getAttribute("data-edge-filter"));
  });
  return types;
}

function initCy() {
  cy = cytoscape({
    container: $("cy"),
    elements: [],
    style: [
      {
        selector: "node",
        style: {
          "label": "data(label)",
          "text-valign": "center",
          "text-halign": "center",
          "font-size": "11px",
          "font-weight": "800",
          "color": "#ffffff",
          "text-outline-width": 2,
          "text-outline-color": "rgba(0,0,0,0.5)",
          "background-color": "#7aa7ff",
          "shape": "ellipse",
          "width": 40,
          "height": 40,
          "border-width": 3,
          "border-color": "rgba(255,255,255,0.2)",
          "overlay-padding": "6px",
          "transition-property": "background-color, border-color, width, height, shadow-blur",
          "transition-duration": "0.3s",
          "text-wrap": "wrap",
          "text-max-width": 140,
          "ghost": "yes",
          "ghost-offset-x": 0,
          "ghost-offset-y": 2,
          "ghost-opacity": 0.2,
        }
      },
      {
        selector: "node[type='Anime']",
        style: {
          "background-color": "#6366f1",
          "border-color": "#818cf8",
          "width": 60,
          "height": 60,
          "shape": "star",
          "font-size": "13px",
        }
      },
      {
        selector: "node[type='Tag']",
        style: {
          "background-color": "#10b981",
          "border-color": "#34d399",
          "width": 45,
          "height": 45,
          "shape": "round-diamond",
        }
      },
      {
        selector: "node[type='Character']",
        style: {
          "background-color": "#f59e0b",
          "border-color": "#fbbf24",
          "width": 50,
          "height": 50,
          "shape": "round-rectangle",
        }
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          "width": 2,
          "line-color": "rgba(255, 255, 255, 0.15)",
          "target-arrow-shape": "triangle",
          "target-arrow-color": "rgba(255, 255, 255, 0.15)",
          "arrow-scale": 1,
          "opacity": 0.8,
          "transition-property": "line-color, width, opacity",
          "transition-duration": "0.3s",
        }
      },
      {
        selector: "edge[type='HAS_TAG']",
        style: {
          "line-style": "dashed",
          "line-color": "rgba(16, 185, 129, 0.4)",
          "target-arrow-color": "rgba(16, 185, 129, 0.4)",
        }
      },
      {
        selector: "edge[type='HAS_CHARACTER']",
        style: {
          "line-style": "dotted",
          "line-color": "rgba(245, 158, 11, 0.4)",
          "target-arrow-color": "rgba(245, 158, 11, 0.4)",
        }
      },
      {
        selector: "edge[type='SIMILAR_TO']",
        style: {
          "line-style": "solid",
          "line-color": "rgba(236, 72, 153, 0.5)",
          "target-arrow-color": "rgba(236, 72, 153, 0.5)",
          "width": 3,
        }
      },
      {
        selector: ".dim",
        style: {
          "opacity": 0.1,
          "text-opacity": 0,
        }
      },
      {
        selector: ".highlightNode",
        style: {
          "border-width": 6,
          "border-color": "#60a5fa",
          "background-color": "#3b82f6",
          "width": 70,
          "height": 70,
        }
      },
      {
        selector: ".highlight",
        style: {
          "opacity": 1,
          "width": 5,
          "line-color": "#60a5fa",
          "target-arrow-color": "#60a5fa",
        }
      }
    ],
    layout: {
      name: "cose",
      animate: true,
      padding: 30,
      idealEdgeLength: 160,
      nodeOverlap: 40,
      refresh: 20,
      fit: true,
      randomize: false,
      componentSpacing: 100,
      nodeRepulsion: 400000,
      edgeElasticity: 100,
      nestingFactor: 5,
      gravity: 80,
      numIter: 1000,
      initialTemp: 200,
      coolingFactor: 0.95,
      minTemp: 1.0,
    },
    wheelSensitivity: 0.2,
    boxSelectionEnabled: false
  });

  cy.on("mouseover", "node", function (evt) {
    const node = evt.target;
    cy.elements().addClass("dim");
    node.removeClass("dim").addClass("highlightNode");
    node.connectedEdges().removeClass("dim");
    node.connectedNodes().removeClass("dim");
  });

  cy.on("mouseout", "node", function () {
    cy.elements().removeClass("dim");
    cy.elements().removeClass("highlightNode");
  });

  cy.on("tap", "node", function (evt) {
    const node = evt.target;
    const type = node.data("type");
    const label = node.data("label");
    if (type === "Anime") {
      selectAnime(label, true);
    }
    if (type === "Tag") {
      highlightViaTag(label);
    }
  });
}

function clearHighlight() {
  if (!cy) return;
  cy.elements().removeClass("dim");
  cy.elements().removeClass("highlight");
  cy.elements().removeClass("highlightNode");
}

function highlightViaTag(tagName) {
  if (!cy) return;
  clearHighlight();
  const tagId = `Tag::${tagName}`;
  const tagNode = cy.getElementById(tagId);
  if (!tagNode || tagNode.empty()) return;
  tagNode.addClass("highlightNode");
  tagNode.connectedEdges().addClass("highlight");
  tagNode.connectedNodes().addClass("highlightNode");
}

function applyEdgeFilters() {
  if (!cy) return;
  const allowed = getEdgeFilters();
  cy.edges().forEach((e) => {
    const type = e.data("type");
    if (allowed.has(type)) e.style("display", "element");
    else e.style("display", "none");
  });
}

function buildElements(graphData) {
  const nodes = (graphData.nodes || []).map((n) => ({
    data: {
      id: n.id,
      label: n.label,
      type: n.type,
    },
  }));
  const edges = (graphData.edges || []).map((e) => ({
    data: {
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.type,
      label: e.label || e.type,
    },
  }));
  return { nodes, edges };
}

function renderGraph(graphData) {
  if (!cy) initCy();
  cy.elements().remove();
  const { nodes, edges } = buildElements(graphData);
  cy.add(nodes);
  cy.add(edges);

  try {
    cy.layout({ name: "cose-bilkent", animate: true, fit: true, padding: 20, randomize: true }).run();
  } catch (e) {
    cy.layout({ name: "cose", animate: true, fit: true, padding: 20, randomize: true }).run();
  }

  applyEdgeFilters();
}

async function apiGet(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });
  try {
    const res = await fetch(url.toString());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error("API GET Error:", e);
    // Only alert if it's a network error or 500
    if (e.message.includes("fetch") || e.message.includes("HTTP 500")) {
      alert("无法连接到后端服务器，请确保已运行 python main.py");
    }
    throw e;
  }
}

async function apiPost(path, body) {
  try {
    const url = new URL(path, window.location.origin);
    const res = await fetch(url.toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error("API POST Error:", e);
    if (e.message.includes("fetch") || e.message.includes("HTTP 500")) {
      alert("无法连接到后端服务器，请确保已运行 python main.py");
    }
    throw e;
  }
}

function setCenterHint(name) {
  $("centerHint").textContent = name ? `中心节点：${name}（点击节点查看详情）` : "点击节点查看详情";
}

async function loadGraph(name, depth = 2) {
  if (!name) return;
  try {
    const graph = await apiGet("/api/graph", { name, depth });
    currentGraph = graph;
    currentCenterName = graph.centerName || name;
    setCenterHint(currentCenterName);
    renderGraph(graph);
    if (graph.centerFound) {
      await loadAnimeDetail(currentCenterName);
    }
  } catch (e) {
    console.error(e);
    setCenterHint(`加载失败：${e.message || e}`);
  }
}

function loadGraphFromInput() {
  const q = $("searchInput").value.trim();
  if (!q) return;
  loadGraph(q, 2);
}

function escapeHtml(s) {
  return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function escapeJsString(s) {
  return String(s).replaceAll("\\", "\\\\").replaceAll("'", "\\'");
}

function renderDetailCard(detail) {
  const title = (detail.anime && (detail.anime.name_cn || detail.anime.name)) ? (detail.anime.name_cn || detail.anime.name) : "";
  const body = detail.found ? `
    <div class="flex items-center justify-between gap-3 mb-4">
      <div>
        <div class="text-lg font-black text-indigo-100">${escapeHtml(title)}</div>
        <div class="text-[10px] text-slate-500 font-bold uppercase tracking-widest mt-1">Properties from Neo4j</div>
      </div>
    </div>

    <div class="space-y-4">
      <div class="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-2">
        ${Object.entries(detail.anime)
          .slice(0, 10)
          .map(([k, v]) => `<div class="flex justify-between gap-3 text-xs"><span class="text-slate-500 font-medium">${escapeHtml(k)}</span><span class="text-slate-300 break-all text-right">${escapeHtml(String(v))}</span></div>`)
          .join("")}
      </div>

      <div class="grid grid-cols-1 gap-4">
        <div>
          <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">作品标签</div>
          <div class="flex flex-wrap gap-1.5">${(detail.tags || []).slice(0, 15).map(t => `<span class="px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold">${escapeHtml(t)}</span>`).join("") || "<div class='text-xs text-slate-500'>暂无标签</div>"}</div>
        </div>
        <div>
          <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">相似推荐</div>
          <div class="grid grid-cols-1 gap-1.5">
            ${(detail.similar || []).slice(0, 5).map(n => `
              <button class="text-left px-3 py-2 rounded-xl bg-slate-900/40 border border-white/5 hover:bg-indigo-500/10 hover:border-indigo-500/20 text-xs text-slate-300 transition-all"
                onclick="selectAnime('${escapeJsString(n)}', true)">${escapeHtml(n)}</button>
            `).join("") || "<div class='text-xs text-slate-500'>暂无推荐</div>"}
          </div>
        </div>
      </div>

      <div>
        <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">角色登场 (部分)</div>
        <div class="flex flex-wrap gap-1.5">
          ${(detail.characters || []).slice(0, 12).map(c => `<span class="px-2 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] font-bold">${escapeHtml(c)}</span>`).join("") || "<div class='text-xs text-slate-500'>暂无角色</div>"}
        </div>
      </div>
    </div>
  ` : `<div class="text-sm text-slate-500 italic">未找到该作品的详细信息。</div>`;
  return body;
}

async function loadAnimeDetail(name) {
  try {
    const detail = await apiGet("/api/anime", { name });
    const html = renderDetailCard(detail);
    $("detailBody").innerHTML = html;
  } catch (e) {
    console.error(e);
  }
}

async function selectAnime(name, openGraph) {
  $("searchInput").value = name;
  if (openGraph) {
    await loadGraph(name, 2);
  }
}

function renderAnimeResults(list, subtitle = "") {
  const body = $("resultsBody");
  body.innerHTML = `
    <div class="text-sm font-bold text-slate-500 uppercase tracking-widest mb-3">${subtitle || "搜索结果"}</div>
    <div class="flex flex-col gap-2">
      ${list.slice(0, 15).map(item => `
        <button class="text-left px-4 py-3 rounded-2xl bg-white/5 border border-white/10 hover:bg-indigo-500/10 hover:border-indigo-500/20 transition-all group"
          onclick="selectAnime('${escapeJsString(item.name)}', true)">
          <div class="font-bold text-base text-slate-200 group-hover:text-indigo-200 transition-colors">${escapeHtml(item.name)}</div>
          <div class="flex items-center gap-3 mt-2">
            ${item.score !== undefined ? `<span class="result-meta text-slate-400">分值: ${item.score}</span>` : ""}
            ${item.rank !== undefined ? `<span class="result-meta text-indigo-300">排名: ${item.rank}</span>` : ""}
          </div>
          ${item.matchedTags && item.matchedTags.length ? `<div class="result-meta text-slate-500 mt-2 leading-relaxed">匹配标签: ${escapeHtml(item.matchedTags.slice(0, 5).join(", "))}</div>` : ""}
        </button>
      `).join("")}
    </div>
  `;
}

async function doRecommend() {
  const id = $("recommendId").value;
  if (!id) return;
  try {
    const res = await apiGet("/api/recommend", { id, limit: 10 });
    renderAnimeResults(res.recommendations || [], `ID ${id} 的相似推荐`);
    if (res.recommendations && res.recommendations.length) {
      await loadGraph(res.recommendations[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">推荐获取失败: ${e.message}</div>`;
  }
}

async function doCasting() {
  const tags = $("castingTags").value.trim();
  if (!tags) return;
  try {
    const res = await apiGet("/api/casting", { tags, limit: 10 });
    const body = $("resultsBody");
    body.innerHTML = `
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">声优查询结果</div>
      <div class="flex flex-col gap-2">
        ${(res.voiceActors || []).map(va => `
          <div class="px-4 py-3 rounded-2xl bg-white/5 border border-white/10">
            <div class="font-bold text-sm text-slate-200">${escapeHtml(va.name)}</div>
            <div class="text-[10px] text-slate-500 mt-1">相关作品数: ${va.score}</div>
          </div>
        `).join("")}
      </div>
    `;
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">声优查询失败: ${e.message}</div>`;
  }
}

async function doCharacterDiscovery() {
  const name = $("characterName").value.trim();
  if (!name) return;
  try {
    const res = await apiGet("/api/character", { name, limit: 20 });
    renderAnimeResults(res.animes || [], `角色 "${res.character || name}" 的登场作品`);
    if (res.animes && res.animes.length) {
      await loadGraph(res.animes[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">角色查询失败: ${e.message}</div>`;
  }
}

async function doStudioStyle() {
  const name = $("studioName").value.trim();
  if (!name) return;
  try {
    const res = await apiGet("/api/studio", { name, limit: 20 });
    renderAnimeResults(res.animes || [], `制作公司 "${res.studio || name}" 的作品`);
    if (res.animes && res.animes.length) {
      await loadGraph(res.animes[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">公司查询失败: ${e.message}</div>`;
  }
}

async function doDiscoverNiche() {
  const rank = $("discoverRank").value;
  const tags = $("discoverTagCount").value;
  if (!rank || !tags) return;
  try {
    const res = await apiGet("/api/discover", { rank, tags, limit: 20 });
    const list = (res.animes || []).map(a => ({
      ...a,
      score: `标签数: ${a.tagCount}`
    }));
    renderAnimeResults(list, `发现: 排名≤${rank}, 标签≥${tags}`);
    if (list.length) {
      await loadGraph(list[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">发现失败: ${e.message}</div>`;
  }
}

function renderRecommendations(recs) {
  const host = $("recommendations");
  host.innerHTML = "";

  (recs || []).forEach((r) => {
    const score = r.score ?? 0;
    const tags = (r.matchedTags || []).slice(0, 6);
    const el = document.createElement("button");
    el.className = "text-left px-4 py-3 rounded-2xl bg-white/5 border border-white/10 hover:bg-purple-500/10 hover:border-purple-500/20 transition-all group";
    el.innerHTML = `
      <div class="font-bold text-sm text-slate-200 group-hover:text-purple-200 transition-colors">${escapeHtml(r.name)}</div>
      <div class="text-[10px] text-slate-500 mt-1">相关分值: ${score}</div>
      <div class="text-[10px] text-slate-500 mt-1.5 leading-relaxed">共同标签: ${tags.length ? escapeHtml(tags.join(", ")) : "无"}</div>
    `;
    el.onclick = () => {
      selectAnime(r.name, true);
    };
    host.appendChild(el);
  });
}

function highlightChatPaths(paths) {
  if (!cy) return;
  clearHighlight();
  (paths || []).slice(0, 2).forEach((p) => {
    (p.edges || []).forEach((ed) => {
      const sel = `edge[source = "${ed.source}"][target = "${ed.target}"][type = "${ed.type}"]`;
      cy.edges().filter(sel).addClass("highlight");
    });
    (p.viaTags || []).slice(0, 8).forEach((t) => {
      const tagNode = cy.getElementById(`Tag::${t}`);
      if (tagNode && !tagNode.empty()) tagNode.addClass("highlightNode");
    });
  });
}

async function sendChat() {
  alert("Button SendChat clicked!");
  const reqId = ++lastChatReqId;
  const inputEl = $("chatInput");
  if (!inputEl) {
    alert("Error: chatInput field not found in HTML!");
    return;
  }
  const input = inputEl.value.trim();
  if (!input) return;

  console.log(`[sendChat] Attempting to send query: ${input}`);
  $("chatAnswer").innerHTML = "<div class='flex items-center gap-2'><span class='animate-pulse'>🤔</span> <span>思考中 (Analyzing graph paths)...</span></div>";
  clearHighlight();

  try {
    const res = await apiPost("/api/chat", { query: input });
    if (reqId !== lastChatReqId) return;

    // Use innerHTML to support potential formatting from LLM (like line breaks)
    $("chatAnswer").innerHTML = (res.answer || "").replace(/\n/g, "<br>");
    renderRecommendations(res.recommendations || []);
    highlightChatPaths(res.graph_paths || []);

    const top = (res.recommendations || [])[0];
    if (top && top.name) {
      loadGraph(top.name, 2);
    }
  } catch (e) {
    console.error("Chat API Error:", e);
    $("chatAnswer").innerHTML = `<div class='text-red-400 font-bold'>❌ 失败: ${escapeHtml(e.message)}</div>`;
  }
}

function clearChat() {
  $("chatInput").value = "";
  $("chatAnswer").textContent = "";
  $("recommendations").innerHTML = "";
  clearHighlight();
}

// Boot
initCy();
setSmartTab('search');

// Optional: auto-load graph by URL param ?name=...
const url = new URL(window.location.href);
const name = url.searchParams.get("name");
if (name) {
  $("searchInput").value = name;
  loadGraph(name, 2);
}
