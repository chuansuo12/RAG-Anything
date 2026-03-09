import {
  uploadBtn,
  startConversationBtn,
  newConversationBtn,
  chatForm,
  tabQaBtn,
  tabKbBtn,
  kbAddBtnEl,
  refPanelCloseBtn,
  refPanelBackdropEl,
  kbDeleteBtn,
  kbRegenerateBtn,
  kbVersionSelectEl,
  uploadGenerateV2El,
  uploadForceV1ThenV2El,
  useAgentModeEl,
  agentVersionWrapEl,
  agentVersionEl,
  renameCurrentConversationBtn,
  currentConversationTitleEl,
} from "./dom.js";
import {
  uploadAndParse,
  loadDocs,
  loadKnowledgeBase,
  showKbUploadSection,
  deleteCurrentKnowledgeBase,
  regenerateCurrentKnowledgeBase,
} from "./kb.js";
import {
  createConversationFromCurrentDoc,
  sendMessage,
  loadConversationList,
  loadConversation,
  resetConversationPlaceholder,
  renameConversation,
} from "./conversations.js";
import { closeRefPanel } from "./refPanel.js";
import { switchView } from "./view.js";
import { setStatus } from "./status.js";
import { appState } from "./state.js";
import { getRouteFromHash, pushRoute } from "./router.js";

/** 根据路由 (view + id + version) 切换界面并加载对应会话/知识库，不写回 hash */
async function applyRoute(route) {
  const r = route || getRouteFromHash();
  switchView(r.view);
  appState.kbVersion = r.version || "v1";
  if (kbVersionSelectEl) kbVersionSelectEl.value = appState.kbVersion;
  if (r.view === "qa") {
    if (r.conversationId) {
      await loadConversation(r.conversationId);
    } else {
      resetConversationPlaceholder();
    }
  } else if (r.view === "kb") {
    if (r.knowledgeId) {
      await loadKnowledgeBase(r.knowledgeId);
    } else if (appState.currentDocId) {
      import("./kbGraph.js").then(({ loadKbGraph }) => loadKbGraph(appState.currentDocId));
    }
  }
}

if (tabQaBtn && tabKbBtn) {
  tabQaBtn.addEventListener("click", () => {
    switchView("qa");
    pushRoute("qa", appState.currentConversationId || null, appState.kbVersion);
  });
  tabKbBtn.addEventListener("click", () => {
    switchView("kb");
    pushRoute("kb", appState.currentDocId || null, appState.kbVersion);
  });
}

if (kbAddBtnEl) {
  kbAddBtnEl.addEventListener("click", () => {
    switchView("kb");
    showKbUploadSection();
    pushRoute("kb", null, appState.kbVersion);
  });
}

if (kbDeleteBtn) {
  kbDeleteBtn.addEventListener("click", deleteCurrentKnowledgeBase);
}

if (kbRegenerateBtn) {
  kbRegenerateBtn.addEventListener("click", regenerateCurrentKnowledgeBase);
}

if (uploadBtn) {
  uploadBtn.addEventListener("click", uploadAndParse);
}

function syncUploadForceToggle() {
  const isV2 = Boolean(uploadGenerateV2El?.checked);
  if (uploadForceV1ThenV2El) {
    uploadForceV1ThenV2El.disabled = !isV2;
    if (!isV2) uploadForceV1ThenV2El.checked = false;
  }
}

if (uploadGenerateV2El) {
  uploadGenerateV2El.addEventListener("change", syncUploadForceToggle);
  syncUploadForceToggle();
}

if (kbVersionSelectEl) {
  kbVersionSelectEl.addEventListener("change", async () => {
    const version = kbVersionSelectEl.value || "v1";
    appState.kbVersion = version;
    pushRoute(appState.currentView, appState.currentView === "kb" ? appState.currentDocId : appState.currentConversationId, version);
    const { loadKbGraph } = await import("./kbGraph.js");
    if (appState.currentDocId) {
      loadKbGraph(appState.currentDocId);
    }
  });
}

if (useAgentModeEl) {
  useAgentModeEl.addEventListener("change", () => {
    appState.useAgent = useAgentModeEl.checked;
    if (agentVersionWrapEl) {
      agentVersionWrapEl.classList.toggle("hidden", !useAgentModeEl.checked);
    }
    if (agentVersionEl) appState.agentVersion = agentVersionEl.value || "v1";
  });
}
if (agentVersionEl) {
  agentVersionEl.addEventListener("change", () => {
    appState.agentVersion = agentVersionEl.value || "v1";
  });
}
if (agentVersionWrapEl) {
  agentVersionWrapEl.classList.toggle("hidden", !useAgentModeEl?.checked);
}

// 保留 startConversationBtn 的引用以避免报错，但不再绑定“使用当前知识库新建会话”的点击事件

if (newConversationBtn) {
  newConversationBtn.addEventListener("click", resetConversationPlaceholder);
}

if (renameCurrentConversationBtn && currentConversationTitleEl) {
  renameCurrentConversationBtn.addEventListener("click", () => {
    const id = appState.currentConversationId;
    if (!id) return;
    const currentTitle = currentConversationTitleEl.textContent || "";
    const newTitle = prompt("输入新的会话名称：", currentTitle);
    if (newTitle !== null && newTitle.trim()) {
      renameConversation(id, newTitle.trim());
    }
  });
}

if (chatForm) {
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });
}

if (refPanelCloseBtn) {
  refPanelCloseBtn.addEventListener("click", closeRefPanel);
}

if (refPanelBackdropEl) {
  refPanelBackdropEl.addEventListener("click", closeRefPanel);
}

function setupProductSchemaControls() {
  const contentEl = document.getElementById("kb-product-schema-content");
  const toggleBtn = document.getElementById("kb-product-schema-toggle");
  const copyBtn = document.getElementById("kb-product-schema-copy");

  if (toggleBtn && contentEl) {
    toggleBtn.addEventListener("click", () => {
      const isHidden = contentEl.classList.toggle("hidden");
      const iconEl = document.getElementById("kb-product-schema-toggle-icon");
      if (iconEl) {
        iconEl.textContent = isHidden ? "▶" : "▼";
      }
    });
  }

  if (copyBtn && contentEl) {
    copyBtn.addEventListener("click", async () => {
      const text = contentEl.textContent || "";
      if (!text.trim()) return;
      try {
        await navigator.clipboard.writeText(text);
        const originalText = copyBtn.textContent || "复制";
        copyBtn.textContent = "已复制";
        setTimeout(() => {
          copyBtn.textContent = originalText;
        }, 1500);
      } catch {
        alert("复制失败，请手动选择文本复制");
      }
    });
  }
}

(async () => {
  setStatus(
    "初始化中...",
    "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
  );
  await loadDocs();
  await loadConversationList();
  setupProductSchemaControls();
  await applyRoute();
  if (!window.location.hash || window.location.hash === "#") {
    const id = appState.currentView === "kb" ? appState.currentDocId : appState.currentConversationId;
    pushRoute(appState.currentView, id || null, appState.kbVersion);
  }
  window.addEventListener("hashchange", () => void applyRoute());
  setStatus("就绪");
})();

