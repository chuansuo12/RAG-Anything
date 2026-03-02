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
} from "./dom.js";
import {
  uploadAndParse,
  loadDocs,
  showKbUploadSection,
  deleteCurrentKnowledgeBase,
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

if (uploadBtn) {
  uploadBtn.addEventListener("click", uploadAndParse);
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

(async () => {
  setStatus(
    "初始化中...",
    "bg-sky-500/10 text-sky-300 border-sky-400/30 px-2 py-1 rounded-full border text-xs",
  );
  await loadDocs();
  await loadConversationList();
  switchView("qa");
  setStatus("就绪");
})();

