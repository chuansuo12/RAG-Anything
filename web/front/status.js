import { statusEl } from "./dom.js";

export function setStatus(text, colorClass) {
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.className =
    "px-2 py-1 rounded-full border text-xs " +
    (colorClass ||
      "bg-emerald-500/10 text-emerald-300 border-emerald-400/30");
}

