/** 界面预览专用的模拟数据，不上传、不训练、不写入真实数据集。 */
import type { DatasetPayload, TimeseriesPayload } from '../api/types'

export function makeOverviewDemo(): { dataset: DatasetPayload; timeseries: TimeseriesPayload } {
  const sheds = ['p1', 'p2', 'p3']
  const positions = Array.from({ length: 12 }, (_, i) => ({
    id: `demo-point-${i + 1}`, x: Number((.15 + i % 4 * .6).toFixed(2)),
    z: [.4, .75, 1.1][Math.floor(i / 4)]!, layer: `L${Math.floor(i / 4) + 1}`,
  }))
  const time = Array.from({ length: 288 }, (_, i) => {
    const day = 10 + Math.floor(i / 48)
    const hour = Math.floor(i % 48 / 2)
    return `2026-10-${day}T${String(hour).padStart(2, '0')}:${i % 2 ? '30' : '00'}:00`
  })
  const bg = time.map((_, i) => Number((23 + 5.5 * Math.sin(i / 48 * Math.PI * 2 - 1.3)).toFixed(2)))
  const mean = Object.fromEntries(sheds.map((shed, j) => [shed,
    bg.map((v, i) => Number((v + 1.3 + j * .8 + .55 * Math.sin(i * .18 + j)).toFixed(2))),
  ]))
  const dataset: DatasetPayload = {
    signature: 'demo-ui-only', file: '界面演示数据（模拟）', n_times: 288, n_columns: 52,
    n_missing: 8, n_dup_times: 0, time_start: time[0]!, time_end: time[time.length - 1]!,
    sheds: { p1: 12, p2: 12, p3: 12 }, positions,
    point_codes: Object.fromEntries(positions.map((point, i) => [point.id, `B${i + 1}`])),
    temperature: sheds.flatMap((shed, j) => positions.map((point, i) => ({
      shed, position: point.id, mean: Number((23.8 + j * .75 + Math.sin(i * .8 + j) * 1.7 + point.z).toFixed(2)),
      min: 18.5 + j * .4, max: 33.5 + j * .7,
    }))),
    fix: { n_rows: 288, fixed_indices: [], monotonic_before: true, monotonic_after: true, spacing_seconds: 1800, n_gaps: 0 },
    checks: [
      { no: 1, name: '时间轴连续性', what: '演示时间轴检查', status: 'ok', evidence: '模拟序列每 30 分钟采集一次' },
      { no: 2, name: '测点数据完整性', what: '演示缺失数据提示', status: 'warn', evidence: '模拟 8 个缺失数据单元，仅用于展示异常样式' },
      { no: 3, name: '重复时刻检查', what: '演示重复检查', status: 'ok', evidence: '模拟序列无重复时刻' },
    ], checks_note: '全部为界面演示数据，不代表真实测量或模型结果。',
  }
  return { dataset, timeseries: {
    n_times: time.length, time, bg_temp: bg, sensors: {}, shed_mean: mean,
    detrended: {}, detrended_mean: {}, detrended_domain: [-3, 3], note: '模拟采集序列，仅用于 UI 预览。',
  } }
}
