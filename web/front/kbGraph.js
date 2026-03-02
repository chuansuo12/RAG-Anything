import {
  kbGraphEl,
  kbGraphEmptyEl,
  kbGraphNodeDetailEl,
  kbGraphNodeDetailContentEl,
} from "./dom.js";
import { appState } from "./state.js";
import { fetchJSON } from "./api.js";

export function clearKbGraph() {
  if (appState.kbGraphNetwork) {
    appState.kbGraphNetwork.destroy();
    appState.kbGraphNetwork = null;
  }

  if (kbGraphEl) {
    kbGraphEl.innerHTML = "";
  }

  if (kbGraphEmptyEl) {
    kbGraphEmptyEl.classList.remove("hidden");
    kbGraphEmptyEl.textContent = "当前知识库尚未生成图数据，或图为空。";
  }

  if (kbGraphNodeDetailEl && kbGraphNodeDetailContentEl) {
    kbGraphNodeDetailContentEl.textContent = "";
    kbGraphNodeDetailEl.classList.add("hidden");
  }
}

export function renderKbGraph(graphData) {
  if (!kbGraphEl) return;

  // vis 由外部脚本注入为全局变量
  // eslint-disable-next-line no-undef
  if (typeof vis === "undefined" || !vis.Network) {
    console.warn("vis-network 未加载，无法渲染知识图谱。");
    return;
  }

  const nodesData = Array.isArray(graphData?.nodes) ? graphData.nodes : [];
  const edgesData = Array.isArray(graphData?.edges) ? graphData.edges : [];

  if (!nodesData.length) {
    clearKbGraph();
    return;
  }

  if (kbGraphEmptyEl) {
    kbGraphEmptyEl.classList.add("hidden");
  }

  // eslint-disable-next-line no-undef
  const nodes = new vis.DataSet(
    nodesData.map((n) => ({
      id: n.id,
      label: n.label || n.id,
      group: n.type || "default",
    })),
  );

  // eslint-disable-next-line no-undef
  const edges = new vis.DataSet(
    edgesData.map((e, idx) => ({
      id: e.id || `${e.source}-${e.target}-${idx}`,
      from: e.source,
      to: e.target,
      value: typeof e.weight === "number" ? e.weight : undefined,
      title: e.description || "",
    })),
  );

  const options = {
    autoResize: true,
    height: "100%",
    width: "100%",
    physics: {
      stabilization: true,
      barnesHut: {
        gravitationalConstant: -2000,
        springLength: 120,
        damping: 0.3,
      },
    },
    nodes: {
      shape: "dot",
      size: 12,
      borderWidth: 1,
      font: { color: "#e2e8f0", size: 11 },
      color: {
        background: "#020617",
        border: "#38bdf8",
        highlight: {
          background: "#020617",
          border: "#f97316",
        },
      },
    },
    edges: {
      color: { color: "#64748b", highlight: "#f97316" },
      width: 1,
      smooth: true,
    },
    interaction: {
      hover: true,
      tooltipDelay: 150,
      zoomView: true,
      dragView: true,
    },
  };

  if (appState.kbGraphNetwork) {
    appState.kbGraphNetwork.destroy();
  }

  // eslint-disable-next-line no-undef
  appState.kbGraphNetwork = new vis.Network(
    kbGraphEl,
    { nodes, edges },
    options,
  );

  appState.kbGraphNetwork.on("selectNode", async (params) => {
    if (!params.nodes || !params.nodes.length) return;
    const nodeId = params.nodes[0];
    if (!kbGraphNodeDetailEl || !kbGraphNodeDetailContentEl) return;

    kbGraphNodeDetailContentEl.textContent = "加载节点详情中...";
    kbGraphNodeDetailEl.classList.remove("hidden");

    try {
      const docId = appState.currentDocId;
      if (!docId) return;
      const detail = await fetchJSON(
        `/api/docs/${encodeURIComponent(
          docId,
        )}/graph/node?node_id=${encodeURIComponent(nodeId)}`,
      );

      const lines = [];
      lines.push(`名称：${detail.label || detail.id}`);
      if (detail.type) {
        lines.push(`类型：${detail.type}`);
      }

      const neighbors = Array.isArray(detail.neighbors)
        ? detail.neighbors
        : [];
      if (neighbors.length) {
        lines.push(`关联节点数：${neighbors.length}`);
        const preview = neighbors
          .slice(0, 20)
          .map((n) => n.label || n.id)
          .join("，");
        if (preview) {
          lines.push(`关联节点示例：${preview}`);
        }
      }

      if (detail.description) {
        lines.push("");
        lines.push("描述：");
        lines.push(detail.description);
      }

      kbGraphNodeDetailContentEl.textContent = lines.join("\n");
    } catch (e) {
      console.error(e);
      kbGraphNodeDetailContentEl.textContent =
        e.message || "加载节点详情失败";
    }
  });

  appState.kbGraphNetwork.on("deselectNode", () => {
    if (kbGraphNodeDetailEl && kbGraphNodeDetailContentEl) {
      kbGraphNodeDetailContentEl.textContent = "";
      kbGraphNodeDetailEl.classList.add("hidden");
    }
  });
}

export async function loadKbGraph(docId) {
  if (!docId || !kbGraphEl) return;
  try {
    const data = await fetchJSON(
      `/api/docs/${encodeURIComponent(docId)}/graph`,
    );
    renderKbGraph(data);
  } catch (e) {
    console.error(e);
    if (kbGraphEmptyEl) {
      kbGraphEmptyEl.textContent = e.message || "加载知识图谱失败";
      kbGraphEmptyEl.classList.remove("hidden");
    }
  }
}

