import {
  conversationListEl,
  currentConversationTitleEl,
  currentDocLabelEl,
  chatMessagesEl,
  chatInput,
  sendBtn,
  docSelectEl,
  kbVersionSelectEl,
  useAgentModeEl,
  agentVersionEl,
  renameCurrentConversationBtn,
} from "./dom.js";
import { appState } from "./state.js";
import { fetchJSON } from "./api.js";
import { setStatus } from "./status.js";
import { loadDocs } from "./kb.js";
import { openRefPanel } from "./refPanel.js";
import { pushRoute } from "./router.js";

export function renderConversationList(items) {
  if (!conversationListEl) return;
  conversationListEl.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "text-xs text-slate-500 py-4 text-center";
    empty.textContent = "暂无会话";
    conversationListEl.appendChild(empty);
    return;
  }
  items.forEach((conv) => {
    const wrapper = document.createElement("div");
    wrapper.className = "relative group";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "w-full text-left px-2 pr-5 py-1.5 rounded-md hover:bg-slate-800/80 text-xs border border-transparent";
    if (conv.conversation_id === appState.currentConversationId) {
      btn.classList.add("bg-slate-800", "border-slate-700");
    }
    const title =
      conv.title || `会话 ${conv.conversation_id.slice(0, 8)}`;
    btn.innerHTML = `
          <div class="font-medium text-slate-100 truncate">${title}</div>
          <div class="text-[10px] text-slate-500 mt-0.5 truncate">知识库: ${conv.doc_id}</div>
        `;
    btn.addEventListener("click", () => {
      loadConversation(conv.conversation_id);
    });

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.className =
      "absolute top-1 right-6 hidden group-hover:inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] text-slate-400 hover:text-cyan-400 hover:bg-slate-800";
    renameBtn.textContent = "✎";
    renameBtn.title = "重命名会话";
    renameBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const newTitle = prompt("输入新的会话名称：", title || "");
      if (newTitle !== null && newTitle.trim()) {
        renameConversation(conv.conversation_id, newTitle.trim());
      }
    });

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className =
      "absolute top-1 right-1 hidden group-hover:inline-flex items-center justify-center w-4 h-4 rounded-full text-[10px] text-slate-400 hover:text-red-400 hover:bg-slate-800";
    delBtn.textContent = "×";
    delBtn.title = "删除该会话";
    delBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(conv.conversation_id);
    });

    wrapper.appendChild(btn);
    wrapper.appendChild(renameBtn);
    wrapper.appendChild(delBtn);
    conversationListEl.appendChild(wrapper);
  });
}

export async function loadConversationList() {
  try {
    const data = await fetchJSON("/api/conversations");
    renderConversationList(data);
  } catch (e) {
    console.error(e);
  }
}

function stageLabel(role, type, name) {
  if (role === "user") return "用户";
  if (role === "assistant" || type === "ai") return "助手";
  if (role === "tool" || type === "tool") return name ? `工具: ${name}` : "工具";
  return role || type || "消息";
}

function appendAgentMessagesBlock(container, agentMessages) {
  if (!agentMessages || !agentMessages.length) return;
  const wrap = document.createElement("div");
  wrap.className = "mt-2 border border-slate-700 rounded-lg overflow-hidden";
  const header = document.createElement("button");
  header.type = "button";
  header.className =
    "w-full text-left px-2 py-1.5 text-[11px] font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-800 flex items-center gap-2";
  const icon = document.createElement("span");
  icon.className = "agent-stages-icon";
  icon.textContent = "▶";
  header.appendChild(icon);
  header.appendChild(
    document.createTextNode(`Agent 阶段 (${agentMessages.length})`)
  );
  const body = document.createElement("div");
  body.className = "agent-stages-body hidden border-t border-slate-700 bg-slate-950/60 max-h-64 overflow-y-auto";
  agentMessages.forEach((m, idx) => {
    const row = document.createElement("div");
    row.className = "px-2 py-1.5 border-b border-slate-800 last:border-b-0";
    const label = document.createElement("div");
    label.className = "text-[10px] font-medium text-cyan-400/90 mb-0.5";
    label.textContent = `${idx + 1}. ${stageLabel(m.role, m.type, m.name)}`;
    row.appendChild(label);
    const pre = document.createElement("pre");
    pre.className = "text-[10px] text-slate-300 whitespace-pre-wrap break-words leading-relaxed";
    pre.textContent = (m.content || "").slice(0, 2000) + (m.content && m.content.length > 2000 ? "\n…" : "");
    row.appendChild(pre);
    body.appendChild(row);
  });
  wrap.appendChild(header);
  wrap.appendChild(body);
  header.addEventListener("click", () => {
    const isOpen = !body.classList.contains("hidden");
    body.classList.toggle("hidden", isOpen);
    icon.textContent = isOpen ? "▶" : "▼";
  });
  container.appendChild(wrap);
}

export function renderMessages(conv) {
  if (!chatMessagesEl) return;
  chatMessagesEl.innerHTML = "";
  const messages = conv.messages || [];
  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "text-xs text-slate-500 text-center py-6";
    empty.textContent =
      "该会话暂无消息，请在下方输入你的第一个问题。";
    chatMessagesEl.appendChild(empty);
    return;
  }

  messages.forEach((msg) => {
    const wrap = document.createElement("div");
    wrap.className =
      "flex " +
      (msg.role === "user" ? "justify-end" : "justify-start");
    const bubble = document.createElement("div");
    bubble.className =
      "max-w-[80%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed";
    if (msg.role === "user") {
      bubble.classList.add("bg-cyan-500", "text-slate-900");
      const hasVersion =
        (msg.kb_version != null && msg.kb_version !== "") ||
        (msg.agent_version != null && msg.agent_version !== "") ||
        msg.use_agent === true;
      if (hasVersion) {
        const versionLabel = document.createElement("div");
        versionLabel.className = "text-[10px] text-slate-600 mt-1";
        const parts = [];
        if (msg.kb_version) parts.push(`知识库 ${msg.kb_version}`);
        if (msg.use_agent) parts.push(msg.agent_version ? `Agent ${msg.agent_version}` : "Agent");
        versionLabel.textContent = parts.length ? parts.join(" · ") : "";
        if (versionLabel.textContent) bubble.appendChild(versionLabel);
      }
    } else {
      bubble.classList.add(
        "bg-slate-800",
        "text-slate-100",
        "border",
        "border-slate-700",
      );
    }
    bubble.textContent = msg.content || "";
    wrap.appendChild(bubble);
    chatMessagesEl.appendChild(wrap);

    if (msg.role === "assistant") {
      if (
        Array.isArray(msg.references) &&
        msg.references.length
      ) {
        const refWrap = document.createElement("div");
        refWrap.className =
          "flex justify-start mt-1 mb-2 ml-1 gap-1 flex-wrap";
        msg.references.forEach((ref, idx) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className =
            "text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300 border border-cyan-500/40 hover:bg-slate-700";
          chip.textContent =
            ref.display_label || ref.label || `引用 ${idx + 1}`;
          chip.addEventListener("click", () => {
            if (!conv.doc_id) {
              alert("未找到绑定知识库，无法查看原文。");
              return;
            }
            openRefPanel(conv.doc_id, ref);
          });
          refWrap.appendChild(chip);
        });
        chatMessagesEl.appendChild(refWrap);
      }
      if (Array.isArray(msg.agent_messages) && msg.agent_messages.length) {
        const agentWrap = document.createElement("div");
        agentWrap.className = "flex justify-start max-w-[80%] ml-0";
        appendAgentMessagesBlock(agentWrap, msg.agent_messages);
        chatMessagesEl.appendChild(agentWrap);
      }
    }
  });
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

export async function loadConversation(conversationId) {
  try {
    setStatus(
      "加载会话中...",
      "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
    );
    const conv = await fetchJSON(
      `/api/conversations/${conversationId}`,
    );
    appState.currentConversationId = conversationId;
    appState.currentDocId = conv.doc_id;
    if (currentConversationTitleEl) {
      currentConversationTitleEl.textContent =
        conv.title || `会话 ${conversationId.slice(0, 8)}`;
    }
    if (renameCurrentConversationBtn) {
      renameCurrentConversationBtn.classList.remove("hidden");
    }
    if (currentDocLabelEl) {
      currentDocLabelEl.textContent = `绑定知识库: ${conv.doc_id}`;
    }
    renderMessages(conv);
    await loadDocs();
    if (docSelectEl) {
      docSelectEl.value = conv.doc_id;
    }
    await loadConversationList();
    pushRoute("qa", conversationId, appState.kbVersion);
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "加载会话失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}

export async function createConversationFromCurrentDoc() {
  const docId = appState.currentDocId || docSelectEl?.value;
  if (!docId) {
    alert("请先选择一个已解析完成的知识库");
    return;
  }
  try {
    setStatus(
      "创建会话中...",
      "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
    );
    const body = JSON.stringify({ doc_id: docId });
    const conv = await fetchJSON("/api/conversations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    appState.currentConversationId = conv.conversation_id;
    appState.currentDocId = conv.doc_id;
    if (currentConversationTitleEl) {
      currentConversationTitleEl.textContent =
        conv.title ||
        `会话 ${conv.conversation_id.slice(0, 8)}`;
    }
    if (renameCurrentConversationBtn) {
      renameCurrentConversationBtn.classList.remove("hidden");
    }
    if (currentDocLabelEl) {
      currentDocLabelEl.textContent = `绑定知识库: ${conv.doc_id}`;
    }
    renderMessages(conv);
    await loadConversationList();
    pushRoute("qa", conv.conversation_id, appState.kbVersion);
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "创建会话失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}

export async function deleteCurrentConversation() {
  const conversationId = appState.currentConversationId;
  if (!conversationId) {
    alert("当前没有选中的会话可供删除");
    return;
  }
  if (!confirm("确定要删除当前会话吗？该操作不可恢复。")) {
    return;
  }

  try {
    setStatus(
      "删除会话中...",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
    await fetchJSON(`/api/conversations/${conversationId}`, {
      method: "DELETE",
    });
    appState.currentConversationId = "";
    resetConversationPlaceholder();
    pushRoute("qa", null, appState.kbVersion);
    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "删除会话失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}

export async function sendMessage() {
  const text = chatInput?.value.trim();
  if (!text) return;
  try {
    if (kbVersionSelectEl) {
      appState.kbVersion = kbVersionSelectEl.value || "v1";
    }
    if (useAgentModeEl) {
      appState.useAgent = useAgentModeEl.checked;
    }
    if (agentVersionEl) {
      appState.agentVersion = agentVersionEl.value || "v1";
    }
    // 如果当前还没有会话，则基于当前选择的知识库自动创建一个新会话
    if (!appState.currentConversationId) {
      const docId = appState.currentDocId || docSelectEl?.value;
      if (!docId) {
        alert("请先选择一个已解析完成的知识库");
        return;
      }
      setStatus(
        "创建会话中...",
        "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
      );
      const body = JSON.stringify({ doc_id: docId });
      const conv = await fetchJSON("/api/conversations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      appState.currentConversationId = conv.conversation_id;
      appState.currentDocId = conv.doc_id;
      if (currentConversationTitleEl) {
        currentConversationTitleEl.textContent =
          conv.title ||
          `会话 ${conv.conversation_id.slice(0, 8)}`;
      }
      if (renameCurrentConversationBtn) {
        renameCurrentConversationBtn.classList.remove("hidden");
      }
      if (currentDocLabelEl) {
        currentDocLabelEl.textContent = `绑定知识库: ${conv.doc_id}`;
      }
      await loadConversationList();
      pushRoute("qa", appState.currentConversationId, appState.kbVersion);
    }

    if (sendBtn) sendBtn.disabled = true;
    if (chatInput) chatInput.disabled = true;
    setStatus(
      "生成回答中...",
      "bg-amber-500/10 text-amber-300 border-amber-400/30 px-2 py-1 rounded-full border text-xs",
    );

    if (chatMessagesEl) {
      const userBubbleWrap = document.createElement("div");
      userBubbleWrap.className = "flex justify-end";
      const userBubble = document.createElement("div");
      userBubble.className =
        "max-w-[80%] rounded-lg px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed bg-cyan-500 text-slate-900";
      userBubble.textContent = text;
      userBubbleWrap.appendChild(userBubble);
      chatMessagesEl.appendChild(userBubbleWrap);
      chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
    }
    if (chatInput) {
      chatInput.value = "";
    }

    const data = await fetchJSON(
      `/api/conversations/${appState.currentConversationId}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          kb_version: appState.kbVersion || "v1",
          use_agent: appState.useAgent || false,
          agent_version: appState.agentVersion || "v1",
        }),
      },
    );

    const answer = data.answer || "";
    const refs = data.references || [];
    const agentMsgs = data.agent_messages || [];
    if (chatMessagesEl) {
      const wrap = document.createElement("div");
      wrap.className = "flex justify-start";
      const inner = document.createElement("div");
      inner.className = "max-w-[80%]";
      const bubble = document.createElement("div");
      bubble.className =
        "rounded-lg px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed bg-slate-800 text-slate-100 border border-slate-700";
      bubble.textContent = answer;
      inner.appendChild(bubble);
      if (refs.length) {
        const refWrap = document.createElement("div");
        refWrap.className = "flex flex-wrap gap-1 mt-1";
        refs.forEach((ref, idx) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className =
            "text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-cyan-300 border border-cyan-500/40 hover:bg-slate-600";
          chip.textContent =
            ref.display_label || ref.label || `引用 ${idx + 1}`;
          chip.addEventListener("click", () => {
            if (!appState.currentDocId) return;
            openRefPanel(appState.currentDocId, ref);
          });
          refWrap.appendChild(chip);
        });
        inner.appendChild(refWrap);
      }
      if (agentMsgs.length) {
        appendAgentMessagesBlock(inner, agentMsgs);
      }
      wrap.appendChild(inner);
      chatMessagesEl.appendChild(wrap);
      chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
    }

    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "发送消息失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    if (chatInput) {
      chatInput.disabled = false;
      chatInput.focus();
    }
  }
}

export function resetConversationPlaceholder() {
  appState.currentConversationId = "";
  pushRoute("qa", null, appState.kbVersion);
  if (currentConversationTitleEl) {
    currentConversationTitleEl.textContent = "新会话尚未创建";
  }
  if (renameCurrentConversationBtn) {
    renameCurrentConversationBtn.classList.add("hidden");
  }
  if (currentDocLabelEl) {
    currentDocLabelEl.textContent =
      "请先在上方选择一个知识库，然后在下方输入你的第一个问题，系统会自动为你创建会话。";
  }
  if (chatMessagesEl) {
    chatMessagesEl.innerHTML =
      '<div class="text-xs text-slate-500 text-center py-6">新会话尚未创建，请先在上方选择好要使用的知识库，然后在下方输入你的第一个问题，系统会自动为你创建会话。</div>';
  }
}

export async function renameConversation(conversationId, newTitle) {
  if (!conversationId || !(newTitle != null && String(newTitle).trim())) {
    return;
  }
  const title = String(newTitle).trim();
  try {
    setStatus(
      "重命名中...",
      "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
    );
    const conv = await fetchJSON(`/api/conversations/${conversationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (appState.currentConversationId === conversationId && currentConversationTitleEl) {
      currentConversationTitleEl.textContent = conv.title || `会话 ${conversationId.slice(0, 8)}`;
    }
    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "重命名会话失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}

async function deleteConversation(conversationId) {
  const id = conversationId || appState.currentConversationId;
  if (!id) {
    alert("当前没有选中的会话可供删除");
    return;
  }
  if (!confirm("确定要删除该会话吗？该操作不可恢复。")) {
    return;
  }

  try {
    setStatus(
      "删除会话中...",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
    await fetchJSON(`/api/conversations/${id}`, {
      method: "DELETE",
    });
    if (appState.currentConversationId === id) {
      appState.currentConversationId = "";
      resetConversationPlaceholder();
      pushRoute("qa", null, appState.kbVersion);
    }
    await loadConversationList();
    setStatus("就绪");
  } catch (e) {
    console.error(e);
    alert(e.message || "删除会话失败");
    setStatus(
      "错误",
      "bg-red-500/10 text-red-300 border-red-400/30 px-2 py-1 rounded-full border text-xs",
    );
  }
}
