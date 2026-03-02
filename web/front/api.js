export async function fetchJSON(url, options = {}) {
  const res = await fetch(url, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    let msg = `请求失败：${res.status}`;
    try {
      const data = await res.json();
      if (data && data.detail) msg = data.detail;
    } catch (_) {
      // ignore
    }
    throw new Error(msg);
  }

  return res.json();
}

