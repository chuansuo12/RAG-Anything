import {
  tabQaBtn,
  tabKbBtn,
  sidebarQaEl,
  sidebarKbEl,
  viewQaEl,
  viewKbEl,
} from "./dom.js";
import { appState } from "./state.js";

export function switchView(view) {
  appState.currentView = view;

  if (view === "qa") {
    if (tabQaBtn && tabKbBtn) {
      tabQaBtn.classList.add("bg-slate-100", "text-slate-900");
      tabQaBtn.classList.remove("bg-transparent", "text-slate-300");
      tabKbBtn.classList.add("bg-transparent", "text-slate-300");
      tabKbBtn.classList.remove("bg-slate-100", "text-slate-900");
    }
    if (sidebarQaEl && sidebarKbEl) {
      sidebarQaEl.classList.remove("hidden");
      sidebarKbEl.classList.add("hidden");
    }
    if (viewQaEl && viewKbEl) {
      viewQaEl.classList.remove("hidden");
      viewKbEl.classList.add("hidden");
    }
  } else {
    if (tabQaBtn && tabKbBtn) {
      tabQaBtn.classList.add("bg-transparent", "text-slate-300");
      tabQaBtn.classList.remove("bg-slate-100", "text-slate-900");
      tabKbBtn.classList.add("bg-slate-100", "text-slate-900");
      tabKbBtn.classList.remove("bg-transparent", "text-slate-300");
    }
    if (sidebarQaEl && sidebarKbEl) {
      sidebarQaEl.classList.add("hidden");
      sidebarKbEl.classList.remove("hidden");
    }
    if (viewQaEl && viewKbEl) {
      viewQaEl.classList.add("hidden");
      viewKbEl.classList.remove("hidden");
    }
  }
}

