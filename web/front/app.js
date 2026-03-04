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
} from "./dom.js";
import {
  uploadAndParse,
  loadDocs,
  showKbUploadSection,
  deleteCurrentKnowledgeBase,
  regenerateCurrentKnowledgeBase,
} from "./kb.js";
import {
  createConversationFromCurrentDoc,
  sendMessage,
  loadConversationList,
  resetConversationPlaceholder,
} from "./conversations.js";
import { closeRefPanel } from "./refPanel.js";
import { switchView } from "./view.js";
import { setStatus } from "./status.js";
import { appState } from "./state.js";

if (tabQaBtn && tabKbBtn) {
  tabQaBtn.addEventListener("click", () => switchView("qa"));
  tabKbBtn.addEventListener("click", () => switchView("kb"));
}

if (kbAddBtnEl) {
  kbAddBtnEl.addEventListener("click", () => {
    switchView("kb");
    showKbUploadSection();
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
    // global version affects graph and next QA message
    appState.kbVersion = kbVersionSelectEl.value || "v1";
    const { loadKbGraph } = await import("./kbGraph.js");
    if (appState.currentDocId) {
      loadKbGraph(appState.currentDocId);
    }
  });
}

// 保留 startConversationBtn 的引用以避免报错，但不再绑定“使用当前知识库新建会话”的点击事件

if (newConversationBtn) {
  newConversationBtn.addEventListener("click", resetConversationPlaceholder);
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
  switchView("qa");
  setStatus("就绪");
})();

