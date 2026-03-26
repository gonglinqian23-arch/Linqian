console.log("Anime Graph Explorer: app_en.js loaded v1.1");

let cy = null;
let currentCenterName = "";
let lastChatReqId = 0;

function $(id) {
  return document.getElementById(id);
}

function setPage(page) {
  const explorer = $("pageExplorer");
  const guide = $("pageGuide");
  const navExplorer = $("navExplorer");
  const navGuide = $("navGuide");

  if (page === "guide" && guide) {
    explorer.classList.add("hidden");
    guide.classList.remove("hidden");
    if (navExplorer) navExplorer.className = "px-5 py-2.5 rounded-xl bg-transparent hover:bg-white/5 text-slate-300 text-sm font-bold transition-all";
    if (navGuide) navGuide.className = "px-5 py-2.5 rounded-xl bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 text-sm font-bold transition-all";
  } else {
    if (guide) guide.classList.add("hidden");
    if (explorer) explorer.classList.remove("hidden");
    if (navGuide) navGuide.className = "px-5 py-2.5 rounded-xl bg-transparent hover:bg-white/5 text-slate-300 text-sm font-bold transition-all";
    if (navExplorer) navExplorer.className = "px-5 py-2.5 rounded-xl bg-indigo-500 text-white shadow-lg shadow-indigo-500/25 text-sm font-bold transition-all";
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
    $("resultsBody").innerHTML = "Run a function to see results here.";
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
    $("resultsBody").innerHTML = "Run a function to see results here.";
  }
  if ($("detailBody")) $("detailBody").innerHTML = "<div class='text-sm text-slate-400 italic'>Click a node in the graph to see details here...</div>";
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
          "shape": "ellipse",
        }
      },
      {
        selector: "node[type='Studio']",
        style: {
          "background-color": "#ec4899",
          "border-color": "#f472b6",
          "width": 60,
          "height": 60,
          "shape": "hexagon",
        }
      },
      {
        selector: "node[type='VoiceActor']",
        style: {
          "background-color": "#fbbf24",
          "border-color": "#fcd34d",
          "width": 65,
          "height": 45,
          "shape": "round-rectangle",
        }
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          "width": 2,
          "line-color": "rgba(255, 255, 255, 0.3)",
          "target-arrow-shape": "triangle",
          "target-arrow-color": "rgba(255, 255, 255, 0.3)",
          "arrow-scale": 1.2,
          "opacity": 0.9,
          "transition-property": "line-color, width, opacity",
          "transition-duration": "0.3s",
        }
      },
      {
        selector: "edge[type='HAS_TAG']",
        style: {
          "line-style": "dashed",
          "line-color": "rgba(16, 185, 129, 0.6)",
          "target-arrow-color": "rgba(16, 185, 129, 0.6)",
        }
      },
      {
        selector: "edge[type='HAS_CHARACTER']",
        style: {
          "line-style": "dotted",
          "line-color": "#f59e0b",
          "target-arrow-color": "#f59e0b",
        }
      },
      {
        selector: "edge[type='SIMILAR_TO']",
        style: {
          "line-style": "solid",
          "line-color": "rgba(236, 72, 153, 0.7)",
          "target-arrow-color": "rgba(236, 72, 153, 0.7)",
          "width": 3,
        }
      },
      {
        selector: "edge[type='VOICED_BY']",
        style: {
          "line-color": "#fbbf24",
          "target-arrow-color": "#fbbf24",
          "line-style": "dashed",
        }
      },
      {
        selector: "edge[type='PRODUCED_BY']",
        style: {
          "line-color": "#ec4899",
          "target-arrow-color": "#ec4899",
          "width": 2,
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
  });

  cy.on("dbltap", "node", async function (evt) {
    const node = evt.target;
    const type = node.data("type");
    const label = node.data("label");
    const id = node.data("id");
    
    // Pulse animation to show loading
    node.animate({ style: { 'width': 85, 'height': 85 } }, { duration: 200 })
        .animate({ style: { 'width': 70, 'height': 70 } }, { duration: 200 });

    try {
      const res = await apiGet("/api/expand", { label, type });
      if (res.nodes && res.nodes.length) {
        const { nodes, edges } = buildElements(res);
        
        // Add only nodes that don't exist
        const newNodes = nodes.filter(n => cy.getElementById(n.data.id).empty());
        const newEdges = edges.filter(e => cy.getElementById(e.data.id).empty());

        if (newNodes.length === 0 && newEdges.length === 0) {
          setCenterHint(`No more new relations for ${label}`);
          setTimeout(() => setCenterHint(null), 2000);
          return;
        }

        cy.add(newNodes);
        cy.add(newEdges);
        
        // Run layout on the whole graph or just the new part
        cy.layout({ 
          name: "cose", 
          animate: true, 
          fit: true, 
          randomize: false,
          padding: 30 
        }).run();
        
        applyEdgeFilters();
        setCenterHint(`Expanded: ${label} (+${newNodes.length} nodes)`);
        setTimeout(() => setCenterHint(null), 3000);
      }
    } catch (e) {
      console.error("Expand Error:", e);
      setCenterHint("Expansion failed");
      setTimeout(() => setCenterHint(null), 2000);
    }
  });
}

function clearHighlight() {
  if (!cy) return;
  cy.elements().removeClass("dim");
  cy.elements().removeClass("highlight");
  cy.elements().removeClass("highlightNode");
}

function applyEdgeFilters() {
  if (!cy) return;
  const checks = document.querySelectorAll("[data-edge-filter]");
  if (checks.length === 0) {
    cy.edges().style("display", "element");
    return;
  }
  
  const allowed = new Set();
  checks.forEach((c) => {
    if (c.checked) allowed.add(c.getAttribute("data-edge-filter"));
  });

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
    if (e.message.includes("fetch") || e.message.includes("HTTP 500")) {
      alert("Unable to connect to backend server. Please ensure python main.py is running.");
    }
    throw e;
  }
}

async function apiPost(path, body) {
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error("API POST Error:", e);
    if (e.message.includes("fetch") || e.message.includes("HTTP 500")) {
      alert("Unable to connect to backend server. Please ensure python main.py is running.");
    }
    throw e;
  }
}

function setCenterHint(name) {
  const el = $("centerHint");
  if (!el) return;
  el.textContent = name ? `Focus: ${name}` : "Click for details • Double-click to expand";
}

async function loadGraph(name, depth = 2) {
  if (!name) return;
  try {
    const graph = await apiGet("/api/graph", { name, depth });
    currentCenterName = graph.centerName || name;
    setCenterHint(currentCenterName);
    renderGraph(graph);
    if (graph.centerFound) {
      await loadAnimeDetail(currentCenterName);
    }
  } catch (e) {
    console.error(e);
    setCenterHint(`Failed: ${e.message || e}`);
  }
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
          <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Tags</div>
          <div class="flex flex-wrap gap-1.5">${(detail.tags || []).slice(0, 15).map(t => `<span class="px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-bold">${escapeHtml(t)}</span>`).join("") || "<div class='text-xs text-slate-500'>No tags</div>"}</div>
        </div>
        <div>
          <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Similar Recommendations</div>
          <div class="grid grid-cols-1 gap-1.5">
            ${(detail.similar || []).slice(0, 5).map(n => `
              <button class="text-left px-3 py-2 rounded-xl bg-slate-900/40 border border-white/5 hover:bg-indigo-500/10 hover:border-indigo-500/20 text-xs text-slate-300 transition-all"
                onclick="selectAnime('${escapeJsString(n)}', true)">${escapeHtml(n)}</button>
            `).join("") || "<div class='text-xs text-slate-500'>No recommendations</div>"}
          </div>
        </div>
      </div>

      <div>
        <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Characters (partial)</div>
        <div class="flex flex-wrap gap-1.5">
          ${(detail.characters || []).slice(0, 12).map(c => `<span class="px-2 py-1 rounded-lg bg-amber-500/10 border border-amber-300/20 text-amber-400 text-[10px] font-bold">${escapeHtml(c)}</span>`).join("") || "<div class='text-xs text-slate-500'>No characters</div>"}
        </div>
      </div>
    </div>
  ` : `<div class="text-sm text-slate-500 italic">No details found.</div>`;
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
    <div class="text-sm font-bold text-slate-500 uppercase tracking-widest mb-3">${subtitle || "Results"}</div>
    <div class="flex flex-col gap-2">
      ${list.slice(0, 15).map(item => `
        <button class="text-left px-4 py-3 rounded-2xl bg-white/5 border border-white/10 hover:bg-indigo-500/10 hover:border-indigo-500/20 transition-all group"
          onclick="selectAnime('${escapeJsString(item.name)}', true)">
          <div class="font-bold text-base text-slate-200 group-hover:text-indigo-200 transition-colors">${escapeHtml(item.name)}</div>
          <div class="flex items-center gap-3 mt-2">
            ${(item.score != null && item.score !== 0) ? `<span class="result-meta text-slate-400">Score: ${item.score}</span>` : ""}
            ${(item.rank != null && item.rank !== 0) ? `<span class="result-meta text-indigo-300">Rank: ${item.rank}</span>` : ""}
          </div>
          ${item.matchedTags && item.matchedTags.length ? `<div class="result-meta text-slate-500 mt-2 leading-relaxed">Tags: ${escapeHtml(item.matchedTags.slice(0, 5).join(", "))}</div>` : ""}
        </button>
      `).join("")}
    </div>
  `;
}

async function doSearch() {
  const q = $("searchInput").value.trim();
  if (!q) return;
  try {
    const res = await apiGet("/api/search", { query: q, limit: 10 });
    renderAnimeResults(res.results || [], `Search: "${q}"`);
    if (res.results && res.results.length) {
      await loadGraph(res.results[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">Search failed: ${e.message}</div>`;
  }
}

async function doRecommend() {
  const id = $("recommendId").value;
  if (!id) return;
  try {
    const res = await apiGet("/api/recommend", { id, limit: 10 });
    renderAnimeResults(res.recommendations || [], `Similar to ID ${id}`);
    if (res.recommendations && res.recommendations.length) {
      await loadGraph(res.recommendations[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">Failed: ${e.message}</div>`;
  }
}

async function doCasting() {
  const tags = $("castingTags").value.trim();
  if (!tags) return;
  try {
    const res = await apiGet("/api/casting", { tags, limit: 10 });
    const body = $("resultsBody");
    body.innerHTML = `
      <div class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Voice Actor Results</div>
      <div class="flex flex-col gap-2">
        ${(res.voiceActors || []).map(va => `
          <div class="px-4 py-3 rounded-2xl bg-white/5 border border-white/10">
            <div class="font-bold text-sm text-slate-200">${escapeHtml(va.name)}</div>
            ${va.score != null ? `<div class="text-[10px] text-slate-500 mt-1">Works count: ${va.score}</div>` : ""}
          </div>
        `).join("")}
      </div>
    `;

    // Render graph for casting results
    if (res.nodes && res.nodes.length) {
      renderGraph(res);
      setCenterHint(`Casting: ${tags}`);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">Failed: ${e.message}</div>`;
  }
}

async function doCharacterDiscovery() {
  const name = $("characterName").value.trim();
  if (!name) return;
  try {
    const res = await apiGet("/api/character", { name, limit: 20 });
    renderAnimeResults(res.animes || [], `Character "${res.character || name}" works`);
    if (res.nodes && res.nodes.length) {
      renderGraph(res);
      setCenterHint(`Character: ${res.character || name}`);
    } else if (res.animes && res.animes.length) {
      await loadGraph(res.animes[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">Failed: ${e.message}</div>`;
  }
}

async function doStudioStyle() {
  const name = $("studioName").value.trim();
  if (!name) return;
  try {
    const res = await apiGet("/api/studio", { name, limit: 20 });
    renderAnimeResults(res.animes || [], `Studio "${res.studio || name}" works`);
    if (res.nodes && res.nodes.length) {
      renderGraph(res);
      setCenterHint(`Studio: ${res.studio || name}`);
    } else if (res.animes && res.animes.length) {
      await loadGraph(res.animes[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">Failed: ${e.message}</div>`;
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
      // Pass tagCount as score if score is 0, so it shows up
      score: a.score || a.tagCount ? `Tags: ${a.tagCount}` : 0
    }));
    renderAnimeResults(list, `Discover: Rank≤${rank}, Tags≥${tags}`);
    if (list.length) {
      await loadGraph(list[0].name, 2);
    }
  } catch (e) {
    $("resultsBody").innerHTML = `<div class="text-xs text-red-400">Failed: ${e.message}</div>`;
  }
}

function renderChatRecommendations(recs) {
  const host = $("recommendations");
  host.innerHTML = "";

  (recs || []).forEach((r) => {
    const score = r.score ?? 0;
    const tags = (r.matchedTags || []).slice(0, 6);
    const el = document.createElement("button");
    el.className = "text-left px-4 py-3 rounded-2xl bg-white/5 border border-white/10 hover:bg-purple-500/10 hover:border-purple-500/20 transition-all group";
    el.innerHTML = `
      <div class="font-bold text-sm text-slate-200 group-hover:text-purple-200 transition-colors">${escapeHtml(r.name)}</div>
      <div class="text-[10px] text-slate-500 mt-1">Score: ${score}</div>
      <div class="text-[10px] text-slate-500 mt-1.5 leading-relaxed">Tags: ${tags.length ? escapeHtml(tags.join(", ")) : "None"}</div>
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
  const reqId = ++lastChatReqId;
  const input = $("chatInput").value.trim();
  if (!input) {
    return;
  }

  $("chatAnswer").innerHTML = "<div class='flex items-center gap-2'><span class='animate-pulse'>🤔</span> <span>Analyzing graph paths...</span></div>";
  clearHighlight();

  try {
    const res = await apiPost("/api/chat", { query: input });
    if (reqId !== lastChatReqId) return;

    $("chatAnswer").innerHTML = (res.answer || "").replace(/\n/g, "<br>");
    
    // Render Keywords/Highlights if available
    if (res.keywords && res.keywords.length) {
      const kwHtml = `
        <div class="mt-4 flex flex-wrap gap-2 pt-4 border-t border-white/5">
          ${res.keywords.map(kw => `
            <span class="px-2.5 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-bold text-indigo-300 uppercase tracking-wider">
              # ${escapeHtml(kw)}
            </span>
          `).join("")}
        </div>
      `;
      $("chatAnswer").innerHTML += kwHtml;
    }

    renderChatRecommendations(res.recommendations || []);
    highlightChatPaths(res.graph_paths || []);

    const top = (res.recommendations || [])[0];
    if (top && top.name) {
      loadGraph(top.name, 2);
    }
  } catch (e) {
    console.error("Chat API Error:", e);
    $("chatAnswer").innerHTML = `<div class='text-red-400 font-bold'>❌ Error: ${escapeHtml(e.message)}</div>`;
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
setPage("explorer");
setSmartTab('search');

// Optional: auto-load graph by URL param ?name=...
const url = new URL(window.location.href);
const name = url.searchParams.get("name");
if (name) {
  loadGraph(name, 2);
}
