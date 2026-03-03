import {
  docSelectEl,
  parseLogEl,
  kbListEl,
  kbDetailMetaEl,
  kbDetailEmptyEl,
  kbDetailEl,
  kbDetailPdfLinkEl,
  kbOverviewSectionEl,
  kbCurrentNameEl,
  kbUploadSectionEl,
  uploadBtn,
  startConversationBtn,
  sendBtn,
  pdfInput,
} from "./dom.js";
import { appState } from "./state.js";
import { fetchJSON } from "./api.js";
import { setStatus } from "./status.js";
import { clearKbGraph, loadKbGraph } from "./kbGraph.js";

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
