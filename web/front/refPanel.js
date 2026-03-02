import {
  refPanelEl,
  refPanelBackdropEl,
  refPanelContentEl,
  refPanelTitleEl,
} from "./dom.js";

export async function openRefPanel(docId, ref) {
  if (!refPanelEl || !refPanelBackdropEl || !refPanelContentEl || !refPanelTitleEl) {
    return;
  }

  const isImage =
    (ref.ref_type === "image" || ref.ref_type === "table") && ref.img_rel_path;
  const pageNum = ref.page_idx != null ? ref.page_idx + 1 : 1;
  const bbox = ref.bbox && ref.bbox.length >= 4 ? ref.bbox : null;

  refPanelTitleEl.textContent = ref.display_label || "引用原文";
  refPanelContentEl.innerHTML =
    '<div class="flex items-center justify-center h-48 text-slate-400">加载中...</div>';

  refPanelEl.classList.remove("translate-x-full");
  refPanelBackdropEl.classList.remove("opacity-0", "pointer-events-none");
  refPanelBackdropEl.classList.add("opacity-100");

  if (isImage) {
    refPanelContentEl.innerHTML = "";
    const img = document.createElement("img");
    img.src = `/api/docs/${encodeURIComponent(
      docId,
    )}/parsed-asset?path=${encodeURIComponent(ref.img_rel_path)}`;
    img.alt = ref.display_label || "";
    img.className = "max-w-full h-auto rounded-lg border border-slate-700";
    refPanelContentEl.appendChild(img);
    return;
  }

  refPanelContentEl.innerHTML = "";
  const wrap = document.createElement("div");
  wrap.className = "relative inline-block";
  const canvas = document.createElement("canvas");
  canvas.className = "border border-slate-700 rounded-lg block";
  wrap.appendChild(canvas);
  const overlay = document.createElement("div");
  overlay.className =
    "absolute pointer-events-none border-2 border-cyan-400 bg-cyan-400/20 rounded";
  overlay.style.display = "none";
  overlay.style.boxSizing = "border-box";
  wrap.appendChild(overlay);
  refPanelContentEl.appendChild(wrap);

  try {
    // pdfjsLib 由外部脚本注入为全局变量
    // eslint-disable-next-line no-undef
    if (typeof pdfjsLib === "undefined") {
      refPanelContentEl.innerHTML =
        '<iframe class="w-full h-[calc(100vh-8rem)] rounded-lg border border-slate-700" src="/api/docs/' +
        encodeURIComponent(docId) +
        "/pdf#page=" +
        pageNum +
        '" title="PDF 原文"></iframe>';
      return;
    }

    // eslint-disable-next-line no-undef
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    // eslint-disable-next-line no-undef
    const pdf = await pdfjsLib.getDocument(
      `/api/docs/${encodeURIComponent(docId)}/pdf`,
    ).promise;
    const page = await pdf.getPage(pageNum);
    const scale = 1.5;
    const viewport = page.getViewport({ scale });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    await page.render({ canvasContext: canvas.getContext("2d"), viewport })
      .promise;

    if (bbox && bbox.length >= 4) {
      const [x1, y1, x2, y2] = bbox;
      const rect = viewport.convertToViewportRectangle([x1, y1, x2, y2]);
      const [rx, ry, rw, rh] = rect;
      overlay.style.left = `${rx}px`;
      overlay.style.top = `${ry}px`;
      overlay.style.width = `${Math.abs(rw)}px`;
      overlay.style.height = `${Math.abs(rh)}px`;
      overlay.style.display = "block";
    }
  } catch (e) {
    console.error(e);
    refPanelContentEl.innerHTML =
      '<iframe class="w-full h-[calc(100vh-8rem)] rounded-lg border border-slate-700" src="/api/docs/' +
      encodeURIComponent(docId) +
      "/pdf#page=" +
      pageNum +
      '" title="PDF 原文"></iframe>';
  }
}

export function closeRefPanel() {
  if (!refPanelEl || !refPanelBackdropEl) return;
  refPanelEl.classList.add("translate-x-full");
  refPanelBackdropEl.classList.add("opacity-0", "pointer-events-none");
  refPanelBackdropEl.classList.remove("opacity-100");
}

