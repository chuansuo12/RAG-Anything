const statusEl = document.getElementById("status-indicator");
const docSelectEl = document.getElementById("doc-select");
const parseLogEl = document.getElementById("parse-log");
const uploadBtn = document.getElementById("upload-btn");
const pdfInput = document.getElementById("pdf-file");
const conversationListEl = document.getElementById("conversation-list");
const newConversationBtn = document.getElementById("new-conversation-btn");
const startConversationBtn = document.getElementById("start-conversation-btn");
const chatMessagesEl = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const currentConversationTitleEl = document.getElementById("current-conversation-title");
const currentDocLabelEl = document.getElementById("current-doc-label");

let currentDocId = "";
let currentConversationId = "";

async function openRefPanel(docId, ref) {
  const panel = document.getElementById("ref-panel");
  const backdrop = document.getElementById("ref-panel-backdrop");
  const content = document.getElementById("ref-panel-content");
  const titleEl = document.getElementById("ref-panel-title");
  const isImage = (ref.ref_type === "image" || ref.ref_type === "table") && ref.img_rel_path;
  const pageNum = ref.page_idx != null ? ref.page_idx + 1 : 1;
  const bbox = ref.bbox && ref.bbox.length >= 4 ? ref.bbox : null;

  titleEl.textContent = ref.display_label || "引用原文";
  content.innerHTML = '<div class="flex items-center justify-center h-48 text-slate-400">加载中...</div>';

  panel.classList.remove("translate-x-full");
  backdrop.classList.remove("opacity-0", "pointer-events-none");
  backdrop.classList.add("opacity-100");

  if (isImage) {
    content.innerHTML = "";
    const img = document.createElement("img");
    img.src = `/api/docs/${encodeURIComponent(docId)}/parsed-asset?path=${encodeURIComponent(ref.img_rel_path)}`;
    img.alt = ref.display_label || "";
    img.className = "max-w-full h-auto rounded-lg border border-slate-700";
    content.appendChild(img);
  } else {
    content.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "relative inline-block";
    const canvas = document.createElement("canvas");
    canvas.className = "border border-slate-700 rounded-lg block";
    wrap.appendChild(canvas);
    const overlay = document.createElement("div");
    overlay.className = "absolute pointer-events-none border-2 border-cyan-400 bg-cyan-400/20 rounded";
    overlay.style.display = "none";
    overlay.style.boxSizing = "border-box";
    wrap.appendChild(overlay);
    content.appendChild(wrap);

    try {
      if (typeof pdfjsLib === "undefined") {
        content.innerHTML = '<iframe class="w-full h-[calc(100vh-8rem)] rounded-lg border border-slate-700" src="/api/docs/' + encodeURIComponent(docId) + '/pdf#page=' + pageNum + '" title="PDF 原文"></iframe>';
        return;
      }
      pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
      const pdf = await pdfjsLib.getDocument(`/api/docs/${encodeURIComponent(docId)}/pdf`).promise;
      const page = await pdf.getPage(pageNum);
      const scale = 1.5;
      const viewport = page.getViewport({ scale });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

      if (bbox && bbox.length >= 4) {
        const [x1, y1, x2, y2] = bbox;
        const rect = viewport.convertToViewportRectangle([x1, y1, x2, y2]);
        const [rx, ry, rw, rh] = rect;
        overlay.style.left = rx + "px";
        overlay.style.top = ry + "px";
        overlay.style.width = Math.abs(rw) + "px";
        overlay.style.height = Math.abs(rh) + "px";
        overlay.style.display = "block";
      }
    } catch (e) {
      console.error(e);
      content.innerHTML = '<iframe class="w-full h-[calc(100vh-8rem)] rounded-lg border border-slate-700" src="/api/docs/' + encodeURIComponent(docId) + '/pdf#page=' + pageNum + '" title="PDF 原文"></iframe>';
    }
  }
}

function closeRefPanel() {
  document.getElementById("ref-panel").classList.add("translate-x-full");
  document.getElementById("ref-panel-backdrop").classList.add("opacity-0", "pointer-events-none");
  document.getElementById("ref-panel-backdrop").classList.remove("opacity-100");
}

function setStatus(text, colorClass) {
  statusEl.textContent = text;
  statusEl.className = "px-2 py-1 rounded-full border text-xs " + (colorClass || "bg-emerald-500/10 text-emerald-300 border-emerald-400/30");
}

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Accept": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let msg = `请求失败：${res.status}`;
    try {
      const data = await res.json();
      if (data && data.detail) msg = data.detail;
    } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

function renderConversationList(items) {
  conversationListEl.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "text-xs text-slate-500 py-4 text-center";
    empty.textContent = "暂无会话";
    conversationListEl.appendChild(empty);
    return;
  }
  items.forEach(conv => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "w-full text-left px-2 py-1.5 rounded-md hover:bg-slate-800/80 text-xs border border-transparent";
    if (conv.conversation_id === currentConversationId) {
      btn.classList.add("bg-slate-800", "border-slate-700");
    }
    const title = conv.title || `会话 ${conv.conversation_id.slice(0, 8)}`;
    btn.innerHTML = `
          <div class="font-medium text-slate-100 truncate">${title}</div>
          <div class="text-[10px] text-slate-500 mt-0.5 truncate">Doc: ${conv.doc_id}</div>
        `;
    btn.addEventListener("click", () => {
      loadConversation(conv.conversation_id);
    });
    conversationListEl.appendChild(btn);
  });
}

async function loadConversationList() {
  try {
    const data = await fetchJSON("/api/conversations");
    renderConversationList(data);
  } catch (e) {
    console.error(e);
  }
}

function renderDocsSelect(docs) {
  const current = docSelectEl.value;
  docSelectEl.innerHTML = '<option value="">选择一个已有文档...</option>';
  docs.forEach(doc => {
    const opt = document.createElement("option");
    opt.value = doc.doc_id;
    opt.textContent = `${doc.file_name || doc.doc_id} (${doc.status})`;
    docSelectEl.appendChild(opt);
  });
  if (current) {
    docSelectEl.value = current;
  }
}

async function loadDocs() {
  try {
    const docs = await fetchJSON("/api/docs");
    renderDocsSelect(docs);
  } catch (e) {
    console.error(e);
  }
}

function renderMessages(conv) {
  chatMessagesEl.innerHTML = "";
  const messages = conv.messages || [];
  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "text-xs text-slate-500 text-center py-6";
    empty.textContent = "该会话暂无消息，请在下方输入你的第一个问题。";
    chatMessagesEl.appendChild(empty);
    return;
  }

  messages.forEach(msg => {
    const wrap = document.createElement("div");
    wrap.className = "flex " + (msg.role === "user" ? "justify-end" : "justify-start");
    const bubble = document.createElement("div");
    bubble.className = "max-w-[80%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed";
    if (msg.role === "user") {
      bubble.classList.add("bg-cyan-500", "text-slate-900");
    } else {
      bubble.classList.add("bg-slate-800", "text-slate-100", "border", "border-slate-700");
    }
    bubble.textContent = msg.content || "";
    wrap.appendChild(bubble);
    chatMessagesEl.appendChild(wrap);

    if (msg.role === "assistant" && Array.isArray(msg.references) && msg.references.length) {
      const refWrap = document.createElement("div");
      refWrap.className = "flex justify-start mt-1 mb-2 ml-1 gap-1 flex-wrap";
      msg.references.forEach((ref, idx) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300 border border-cyan-500/40 hover:bg-slate-700";
        chip.textContent = ref.display_label || ref.label || `引用 ${idx + 1}`;
        chip.addEventListener("click", () => {
          if (!conv.doc_id) {
            alert("未找到绑定文档，无法查看原文。");
            return;
          }
          openRefPanel(conv.doc_id, ref);
        });
        refWrap.appendChild(chip);
      });
      chatMessagesEl.appendChild(refWrap);
    }
  });
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

async function loadConversation(conversationId) {
  try {
    setStatus("加载会话中...", "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs");
    const conv = await fetchJSON(`/api/conversations/${conversationId}`);
    currentConversationId = conversationId;
    currentDocId = conv.doc_id;
    currentConversationTitleEl.textContent = conv.title || `会话 ${conversationId.slice(0, 8)}`;
    currentDocLabelEl.textContent = `绑定文档: ${conv.doc_id}`;
    renderMessages(conv);
    await loadDocs();
    docSelectEl.value = conv.doc_id;
    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "加载会话失败");
    setStatus("错误", "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs");
  }
}

async function uploadAndParse() {
  const file = pdfInput.files && pdfInput.files[0];
  if (!file) {
    alert("请选择一个 PDF 文件");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);

  try {
    setStatus("解析中...", "bg-amber-500/10 text-amber-300 border-amber-400/30 px-2 py-1 rounded-full border text-xs");
    uploadBtn.disabled = true;
    startConversationBtn.disabled = true;
    sendBtn.disabled = true;
    parseLogEl.textContent = "正在上传并解析，请稍候...";

    const data = await fetchJSON("/api/docs/upload", {
      method: "POST",
      body: formData,
    });

    const meta = data.meta || {};
    currentDocId = data.doc_id;
    parseLogEl.textContent = (meta.log || []).join("\n");
    await loadDocs();
    docSelectEl.value = currentDocId;
    setStatus("解析完成");
    startConversationBtn.disabled = false;
  } catch (e) {
    console.error(e);
    parseLogEl.textContent = `解析失败：${e.message || e}`;
    setStatus("错误", "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs");
  } finally {
    uploadBtn.disabled = false;
    sendBtn.disabled = false;
  }
}

async function createConversationFromCurrentDoc() {
  const docId = currentDocId || docSelectEl.value;
  if (!docId) {
    alert("请先选择或上传一个已解析的文档");
    return;
  }
  try {
    setStatus("创建会话中...", "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs");
    const body = JSON.stringify({ doc_id: docId });
    const conv = await fetchJSON("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    currentConversationId = conv.conversation_id;
    currentDocId = conv.doc_id;
    currentConversationTitleEl.textContent = conv.title || `会话 ${conv.conversation_id.slice(0, 8)}`;
    currentDocLabelEl.textContent = `绑定文档: ${conv.doc_id}`;
    renderMessages(conv);
    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "创建会话失败");
    setStatus("错误", "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs");
  }
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  if (!currentConversationId) {
    alert("请先新建或选择一个会话");
    return;
  }
  try {
    sendBtn.disabled = true;
    chatInput.disabled = true;
    setStatus("生成回答中...", "bg-amber-500/10 text-amber-300 border-amber-400/30 px-2 py-1 rounded-full border text-xs");

    // Optimistic render user message
    const userBubbleWrap = document.createElement("div");
    userBubbleWrap.className = "flex justify-end";
    const userBubble = document.createElement("div");
    userBubble.className = "max-w-[80%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed bg-cyan-500 text-slate-900";
    userBubble.textContent = text;
    userBubbleWrap.appendChild(userBubble);
    chatMessagesEl.appendChild(userBubbleWrap);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
    chatInput.value = "";

    const data = await fetchJSON(`/api/conversations/${currentConversationId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text }),
    });

    const answer = data.answer || "";
    const refs = data.references || [];
    const wrap = document.createElement("div");
    wrap.className = "flex justify-start";
    const inner = document.createElement("div");
    inner.className = "max-w-[80%]";
    const bubble = document.createElement("div");
    bubble.className = "rounded-lg px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed bg-slate-800 text-slate-100 border border-slate-700";
    bubble.textContent = answer;
    inner.appendChild(bubble);
    if (refs.length) {
      const refWrap = document.createElement("div");
      refWrap.className = "flex flex-wrap gap-1 mt-1";
      refs.forEach((ref, idx) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-cyan-300 border border-cyan-500/40 hover:bg-slate-600";
        chip.textContent = ref.display_label || ref.label || `引用 ${idx + 1}`;
        chip.addEventListener("click", () => {
          if (!currentDocId) return;
          openRefPanel(currentDocId, ref);
        });
        refWrap.appendChild(chip);
      });
      inner.appendChild(refWrap);
    }
    wrap.appendChild(inner);
    chatMessagesEl.appendChild(wrap);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "发送消息失败");
    setStatus("错误", "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs");
  } finally {
    sendBtn.disabled = false;
    chatInput.disabled = false;
    chatInput.focus();
  }
}

// Event bindings
uploadBtn.addEventListener("click", uploadAndParse);
startConversationBtn.addEventListener("click", createConversationFromCurrentDoc);
newConversationBtn.addEventListener("click", () => {
  currentConversationId = "";
  currentConversationTitleEl.textContent = "新会话尚未创建";
  currentDocLabelEl.textContent = "请选择或上传 PDF 后点击上方按钮创建会话。";
  chatMessagesEl.innerHTML = '<div class="text-xs text-slate-500 text-center py-6">新会话尚未创建，请先选择或上传文档。</div>';
});

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage();
});

document.getElementById("ref-panel-close").addEventListener("click", closeRefPanel);
document.getElementById("ref-panel-backdrop").addEventListener("click", closeRefPanel);

// Initial load
(async () => {
  setStatus("初始化中...", "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs");
  await loadDocs();
  await loadConversationList();
  setStatus("就绪");
})();

