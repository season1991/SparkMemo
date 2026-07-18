/**
 * DSP 文件名解析：截掉扩展名后按 '-' 切分，取前 3 段。
 *
 * 与后端 `backend/app/services/dsp_parser.py:parse_filename` 规则一致：
 * 1. 空字符串 / 缺段 → 抛 Error；
 * 2. 'foo-bar.xlsx' → 抛 Error（仅 2 段 < 3）；
 * 3. 'a-b-c.xlsx' → ('a', 'b', 'c')；
 * 4. 'a-b-c-d.xlsx' → 取前 3 段 ('a', 'b', 'c')，第 4 段及之后丢弃；
 * 5. 'foo-bar'（无扩展名）→ 'foo-bar' 视为整串，split('-') → 2 段 < 3 → 抛 Error。
 *
 * **v0.5.1 状态**：解析结果仅作前端 UI 初值填充，不再作为 POST 上传字段来源
 * （上传时以用户在表单内编辑后的值为准）。
 *
 * @param {string} filename 浏览器拿到的 File.name
 * @returns {{ vendor: string, item: string, sub_item: string }}
 * @throws {Error} 文件名无法解析为 ≥3 段时
 */
export function parseFilename(filename) {
  if (!filename) {
    throw new Error('filename is required')
  }
  const stem = filename.includes('.')
    ? filename.split('.').slice(0, -1).join('.')
    : filename
  const parts = stem.split('-')
  if (parts.length < 3) {
    throw new Error('filename must contain at least 3 segments separated by "-"')
  }
  return { vendor: parts[0], item: parts[1], sub_item: parts[2] }
}
