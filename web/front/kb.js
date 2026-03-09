import {
  docSelectEl,
  parseLogEl,
  kbListEl,
  kbDetailMetaEl,
  kbDetailEmptyEl,
  kbDetailEl,
  kbDetailPdfLinkEl,
  kbProductSchemaSectionEl,
  kbProductSchemaContentEl,
  kbOverviewSectionEl,
  kbCurrentNameEl,
  kbUploadSectionEl,
  uploadBtn,
  startConversationBtn,
  sendBtn,
  pdfInput,
  uploadGenerateV2El,
  uploadForceV1ThenV2El,
  kbRegenerateBtn,
  kbVersionSelectEl,
} from "./dom.js";
import { appState } from "./state.js";
import { fetchJSON } from "./api.js";
import { setStatus } from "./status.js";
import { clearKbGraph, loadKbGraph } from "./kbGraph.js";
import { pushRoute } from "./router.js";

let productSchemaFetchToken = 0;

async function loadProductSchemaForDoc(docId) {
  const token = ++productSchemaFetchToken;

  if (!kbProductSchemaSectionEl || !kbProductSchemaContentEl) return;

  const hide = () => {
    kbProductSchemaSectionEl.classList.add("hidden");
    kbProductSchemaContentEl.textContent = "";
    kbProductSchemaContentEl.classList.add("hidden");
    const toggleIcon = document.getElementById("kb-product-schema-toggle-icon");
    if (toggleIcon) {
      toggleIcon.textContent = "▶";
    }
  };

  if (!docId) {
    hide();
    return;
  }

  try {
    const url = `/api/docs/${encodeURIComponent(
      docId,
    )}/product-schema?t=${Date.now()}`;
    const data = await fetchJSON(url, { cache: "no-store" });
    if (token !== productSchemaFetchToken) return;

    const text =
      typeof data === "string" ? data : JSON.stringify(data, null, 2);
    kbProductSchemaContentEl.textContent = text;
    kbProductSchemaContentEl.classList.add("hidden");
    kbProductSchemaSectionEl.classList.remove("hidden");
  } catch (e) {
    if (token !== productSchemaFetchToken) return;
    const msg = String(e?.message || e || "");
    const isNotFound =
      msg.includes("404") ||
      msg.includes("尚未生成 product info") ||
      msg.includes("未找到 v2 工作目录") ||
      msg.includes("product info（v2）");
    if (isNotFound) {
      hide();
      return;
    }

    // Unexpected error: show panel with error text for visibility
    kbProductSchemaContentEl.textContent = `加载 product info 失败：${msg}`;
    kbProductSchemaSectionEl.classList.remove("hidden");
  }
}

export function renderDocsSelect(docs) {
  if (!docSelectEl) return;
  const current = docSelectEl.value;
  docSelectEl.innerHTML = '<option value="">选择一个已有知识库...</option>';
  docs.forEach((doc) => {
    const opt = document.createElement("option");
    opt.value = doc.doc_id;
    opt.textContent = `${doc.file_name || doc.doc_id} (${doc.status})`;
    docSelectEl.appendChild(opt);
  });
  if (current) {
    docSelectEl.value = current;
  }
}

export function renderKbList(docs) {
  if (!kbListEl) return;
  kbListEl.innerHTML = "";
  if (!docs.length) {
    const empty = document.createElement("div");
    empty.className = "text-xs text-slate-500 py-4 text-center";
    empty.textContent = "暂无知识库";
    kbListEl.appendChild(empty);
    return;
  }
  docs.forEach((doc) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "w-full text-left px-2 py-1.5 rounded-md hover:bg-slate-800/80 text-xs border border-transparent";
    if (doc.doc_id === appState.currentDocId) {
      btn.classList.add("bg-slate-800", "border-slate-700");
    }
    const name = doc.file_name || doc.doc_id;
    const status = doc.status || "unknown";
    const createdAt = doc.created_at || "";
    btn.innerHTML = `
          <div class="font-medium text-slate-100 truncate">${name}</div>
          <div class="text-[10px] text-slate-500 mt-0.5 truncate">状态: ${status}${
            createdAt ? " · " + createdAt : ""
          }</div>
        `;
    btn.addEventListener("click", () => {
      loadKnowledgeBase(doc.doc_id);
    });
    kbListEl.appendChild(btn);
  });
}

export async function loadDocs() {
  try {
    const docs = await fetchJSON("/api/docs");
    renderDocsSelect(docs);
    renderKbList(docs);
  } catch (e) {
    console.error(e);
  }
}

export function updateKbDetail(meta) {
  if (!kbDetailMetaEl || !kbDetailEmptyEl || !kbDetailEl) return;
  const docId = meta.doc_id || appState.currentDocId || "";
  const fileName = meta.file_name || docId;
  const status = meta.status || "unknown";
  const createdAt = meta.created_at || "";
  const lines = [
    `名称：${fileName}`,
    `ID：${docId}`,
    `状态：${status}`,
  ];
  if (createdAt) {
    lines.push(`创建时间：${createdAt}`);
  }
  const log = Array.isArray(meta.log) ? meta.log : [];
  if (log.length) {
    lines.push("", "最近日志：");
    const tail = log.slice(-5);
    tail.forEach((line) => lines.push(line));
  }
  kbDetailMetaEl.textContent = lines.join("\n");
  kbDetailEmptyEl.classList.add("hidden");
  kbDetailEl.classList.remove("hidden");

  if (kbDetailPdfLinkEl) {
    if (docId) {
      kbDetailPdfLinkEl.href = `/api/docs/${encodeURIComponent(docId)}/pdf`;
      kbDetailPdfLinkEl.classList.remove(
        "pointer-events-none",
        "opacity-50",
      );
    } else {
      kbDetailPdfLinkEl.href = "#";
      kbDetailPdfLinkEl.classList.add("pointer-events-none", "opacity-50");
    }
  }

  loadProductSchemaForDoc(docId);

  if (parseLogEl) {
    parseLogEl.textContent = log.join("\n");
  }

  if (kbUploadSectionEl) {
    kbUploadSectionEl.classList.add("hidden");
  }
  if (kbOverviewSectionEl) {
    kbOverviewSectionEl.classList.remove("hidden");
  }

  if (docId) {
    loadKbGraph(docId);
  } else {
    clearKbGraph();
  }

  if (kbCurrentNameEl) {
    kbCurrentNameEl.textContent = fileName || "";
  }
}

export async function loadKnowledgeBase(docId) {
  try {
    setStatus(
      "加载知识库中...",
      "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
    );
    const meta = await fetchJSON(`/api/docs/${encodeURIComponent(docId)}`);
    appState.currentDocId = meta.doc_id || docId;
    updateKbDetail(meta);
    await loadDocs();
    pushRoute("kb", appState.currentDocId, appState.kbVersion);
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "加载知识库失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}

export function showKbUploadSection() {
  if (!kbUploadSectionEl) return;
  kbUploadSectionEl.classList.remove("hidden");
  if (kbOverviewSectionEl) {
    kbOverviewSectionEl.classList.add("hidden");
  }
  if (kbDetailEl) {
    kbDetailEl.classList.add("hidden");
  }
  if (kbDetailEmptyEl) {
    kbDetailEmptyEl.classList.remove("hidden");
  }
  if (pdfInput) {
    pdfInput.value = "";
  }
  if (parseLogEl) {
    parseLogEl.textContent = "";
  }
  kbUploadSectionEl.scrollIntoView({ behavior: "smooth", block: "start" });
}

export async function uploadAndParse() {
  const file = pdfInput?.files && pdfInput.files[0];
  if (!file) {
    alert("请选择一个要加入知识库的 PDF 文件");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  const includeV2 = Boolean(uploadGenerateV2El?.checked);
  formData.append("kb_version", includeV2 ? "v2" : "v1");
  const forceFlag = includeV2 ? Boolean(uploadForceV1ThenV2El?.checked) : false;
  formData.append("force_v1_then_v2", forceFlag ? "true" : "false");

  try {
    setStatus(
      "解析中...",
      "bg-amber-500/10 text-amber-300 border-amber-400/30 px-2 py-1 rounded-full border text-xs",
    );
    if (uploadBtn) uploadBtn.disabled = true;
    if (startConversationBtn) startConversationBtn.disabled = true;
    if (sendBtn) sendBtn.disabled = true;
    if (parseLogEl) {
      parseLogEl.textContent = "正在上传并解析为知识库，请稍候...";
    }

    const data = await fetchJSON("/api/docs/upload", {
      method: "POST",
      body: formData,
    });

    const meta = data.meta || {};
    appState.currentDocId = data.doc_id;
    if (parseLogEl) {
      parseLogEl.textContent = (meta.log || []).join("\n");
    }
    await loadDocs();
    if (docSelectEl) {
      docSelectEl.value = appState.currentDocId;
    }
    setStatus("知识库解析完成");
    if (startConversationBtn) {
      startConversationBtn.disabled = false;
    }
  } catch (e) {
    console.error(e);
    if (parseLogEl) {
      parseLogEl.textContent = `解析失败：${e.message || e}`;
    }
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  } finally {
    if (uploadBtn) uploadBtn.disabled = false;
    if (sendBtn) sendBtn.disabled = false;
  }
}

export async function deleteCurrentKnowledgeBase() {
  const docId = appState.currentDocId || docSelectEl?.value;
  if (!docId) {
    alert("当前没有选中的知识库可供删除");
    return;
  }
  if (!confirm("确定要删除当前知识库及其关联会话吗？该操作不可恢复。")) {
    return;
  }

  try {
    setStatus(
      "删除知识库中...",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
    await fetchJSON(`/api/docs/${encodeURIComponent(docId)}`, {
      method: "DELETE",
    });

    if (docSelectEl) {
      docSelectEl.value = "";
    }
    if (appState.currentDocId === docId) {
      appState.currentDocId = "";
      pushRoute("kb", null, appState.kbVersion);
    }
    await loadDocs();

    if (kbDetailMetaEl) {
      kbDetailMetaEl.textContent = "";
    }
    if (kbDetailEl) {
      kbDetailEl.classList.add("hidden");
    }
    if (kbDetailEmptyEl) {
      kbDetailEmptyEl.classList.remove("hidden");
    }
    clearKbGraph();

    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "删除知识库失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}

export async function regenerateCurrentKnowledgeBase() {
  const docId = appState.currentDocId || docSelectEl?.value;
  if (!docId) {
    alert("请先选择一个知识库");
    return;
  }
  const includeV2 = (appState.kbVersion || kbVersionSelectEl?.value || "v1") === "v2";
  if (!includeV2) {
    const ok = confirm("确定要重新生成索引吗？\n\n该操作会重建 v1 索引。");
    if (!ok) return;
  }
  try {
    setStatus(
      includeV2 ? "生成 v2 中..." : "重新生成中...",
      "bg-amber-500/10 text-amber-300 border-amber-400/30 px-2 py-1 rounded-full border text-xs",
    );
    if (kbRegenerateBtn) kbRegenerateBtn.disabled = true;

    let res;
    if (includeV2) {
      // v2 模式：只生成/更新 v2（不重建 v1）
      const fd = new FormData();
      fd.append("force_v1_then_v2", "false");
      res = await fetchJSON(`/api/docs/${encodeURIComponent(docId)}/generate-v2`, {
        method: "POST",
        body: fd,
      });
    } else {
      // v1 模式：重建 v1
      const fd = new FormData();
      fd.append("include_v2", "false");
      res = await fetchJSON(`/api/docs/${encodeURIComponent(docId)}/regenerate`, {
        method: "POST",
        body: fd,
      });
    }

    const meta = res.meta || {};
    updateKbDetail(meta);
    await loadDocs();
    setStatus(includeV2 ? "v2 生成完成" : "重新生成完成");
  } catch (e) {
    console.error(e);
    alert(e.message || (includeV2 ? "生成 v2 失败" : "重新生成失败"));
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  } finally {
    if (kbRegenerateBtn) kbRegenerateBtn.disabled = false;
  }
}
