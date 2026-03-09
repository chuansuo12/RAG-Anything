/**
 * Hash 路由：qa/{conversationId}/{version}、kb/{knowledgeId}/{version}，刷新后恢复视图/会话/知识库/版本。
 * 格式：#/qa | #/qa/{conversationId} | #/qa/{conversationId}/v1 | #/kb | #/kb/{knowledgeId} | #/kb/{knowledgeId}/v2
 */

const HASH_PREFIX = "#/";
const VERSIONS = ["v1", "v2"];

/**
 * 从当前 location.hash 解析出 { view, conversationId?, knowledgeId?, version }
 * @returns {{ view: 'qa'|'kb', conversationId?: string|null, knowledgeId?: string|null, version: 'v1'|'v2' }}
 */
export function getRouteFromHash() {
  const raw = typeof window !== "undefined" ? window.location.hash : "";
  const path = raw.startsWith(HASH_PREFIX) ? raw.slice(HASH_PREFIX.length).replace(/^\/+|\/+$/g, "") : "";
  const parts = path ? path.split("/") : [];

  let view = "qa";
  let conversationId = null;
  let knowledgeId = null;
  let version = "v1";

  try {
    if (parts[0] === "kb") {
      view = "kb";
      if (parts.length >= 3) {
        knowledgeId = decodeURIComponent(parts[1]);
        if (VERSIONS.includes(parts[2])) version = parts[2];
      } else if (parts.length === 2) {
        if (VERSIONS.includes(parts[1])) version = parts[1];
        else knowledgeId = decodeURIComponent(parts[1]);
      }
    } else if (parts[0] === "qa") {
      view = "qa";
      if (parts.length >= 3) {
        conversationId = decodeURIComponent(parts[1]);
        if (VERSIONS.includes(parts[2])) version = parts[2];
      } else if (parts.length === 2) {
        if (VERSIONS.includes(parts[1])) version = parts[1];
        else conversationId = decodeURIComponent(parts[1]);
      }
    }
  } catch (_) {
    if (parts[0] === "kb" && parts[1] && !VERSIONS.includes(parts[1])) knowledgeId = parts[1];
    if (parts[0] === "qa" && parts[1] && !VERSIONS.includes(parts[1])) conversationId = parts[1];
    if (parts[2] && VERSIONS.includes(parts[2])) version = parts[2];
    if (parts.length === 2 && VERSIONS.includes(parts[1])) version = parts[1];
  }

  return { view, conversationId, knowledgeId, version };
}

/**
 * 将当前 view + id + version 写入 URL hash（不触发 reload）
 * @param {'qa'|'kb'} view
 * @param {string|null|undefined} id - 会话 id（qa）或知识库 doc_id（kb），无则只写 view
 * @param {'v1'|'v2'|string|null|undefined} version - 可选，默认 v1
 */
export function pushRoute(view, id, version) {
  const base = view === "kb" ? "kb" : "qa";
  const v = version && VERSIONS.includes(version) ? version : "v1";
  let path = base;
  if (id) path += `/${encodeURIComponent(id)}`;
  path += `/${v}`;
  const hash = HASH_PREFIX + path;
  const fullUrl = window.location.pathname + window.location.search + hash;
  if (window.location.hash !== hash) {
    window.history.replaceState(null, "", fullUrl);
  }
}
