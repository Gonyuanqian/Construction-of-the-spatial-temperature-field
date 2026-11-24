import type { ModelRowPayload } from '../api/types'

export const emptyModelFilters = () => ({ name: '', source: '', artifact: '', fit: '', start: '', end: '' })
export type ModelFilters = ReturnType<typeof emptyModelFilters>
export function filterModels(rows: ModelRowPayload[], filters: ModelFilters): ModelRowPayload[] {
  const name = filters.name.trim().toLocaleLowerCase()
  return rows.filter(row => (!name || row.name.toLocaleLowerCase().includes(name))
    && (!filters.source || row.data_file === filters.source)
    && (!filters.artifact || row.has_artifact === (filters.artifact === 'ready'))
    && (!filters.fit || (filters.fit === 'native' ? row.compatible && !row.borrowed
      : filters.fit === 'borrowed' ? row.compatible && row.borrowed : !row.compatible))
    && (!filters.start || row.saved_at.slice(0, 10) >= filters.start)
    && (!filters.end || row.saved_at.slice(0, 10) <= filters.end))
}

/** 列表导出只含管理信息；转义 CSV，并阻止表格软件把用户名称解释成公式。 */
export function modelListCsv(rows: ModelRowPayload[]): string {
  const cell = (value: unknown) => {
    let text = value == null ? '' : String(value)
    if (/^[\s]*[=+@\-]/.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  return '\uFEFF' + [
    ['ID', '模型名称', '训练来源', '成品状态', 'MAE / ℃', '保存时间'],
    ...rows.map(row => [row.id, row.name, row.data_file, row.has_artifact ? '已保存成品' : '仅保存参数', row.mae, row.saved_at]),
  ].map(row => row.map(cell).join(',')).join('\r\n')
}
