/**
 * 浏览器原生下载工具（v0.5.8）。
 *
 * 把 Blob / Response 二进制触发为浏览器下载。
 * 步骤：URL.createObjectURL → 动态创建 <a download> → click() → revokeObjectURL。
 *
 * 注意事项：
 * - 必须 revokeObjectURL，否则 blob 内存泄漏（特别是频繁下载场景）
 * - filename 仅作 <a download> 属性；HTTP 响应的 Content-Disposition 优先（spec §6.2）
 * - 在 jsdom 中调用不会真正下载，但 URL.createObjectURL 可被 spy 验证
 *
 * @param {Blob} blob 浏览器 Blob 对象（来自 axios responseType:'blob'）
 * @param {string} filename 下载文件名（不含路径）
 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}