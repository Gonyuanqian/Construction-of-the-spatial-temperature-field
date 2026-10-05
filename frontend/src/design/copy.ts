/**
 * 全站文案的单一来源。
 *
 * 标题改过一次（「预测」→「重建」，spec 2026-10-04 §六 第 6 项）：实时模式按设计是
 * **用当下数据算当下的构场**，不是外推未来，而「未来预测」被明确划在范围外。
 * 这个名字同时出现在 copy.ts、index.html 和若干组件里 —— 写死三份就会漂成两个名字，
 * 而验收时看到的正是它。所以有一条测试扫全仓来守。
 */
export const SYSTEM_TITLE = '棚式空间温度场重建系统'

/**
 * 顶部模式开关的两项。实时模式现在**开着了**：后端扩库与重标定都做完了，
 * 它自己那一屏在 `/live`（路由懒加载，见 `router/index.ts`）。
 */
export const MODES = [
  { key: 'train', label: '训练模式', enabled: true, why: '' },
  // `why` 留着空串而不是删掉字段：类型上它必填，而 `guards.test.ts` 那条
  // 「未开放项必带理由」的循环按 `enabled` 跳过这一项 —— 删字段是改类型，
  // 换不来什么。
  { key: 'live', label: '实时模式', enabled: true, why: '' },
] as const

/**
 * 左侧导航。**次序就是流水线的次序** —— 数据可信 → 特征与参数定下来 → 场长出来 →
 * 误差有多大。顺序本身是信息，不许改成按字母或按使用频率排。
 *
 * 未开放的两项**留位并说明**，不做成空页：空页比没有更难看
 * （spec 2026-10-04 §二.4）。
 */
export const NAV_ITEMS = [
  { key: 'data', label: '数据导入与检查', to: '/data', enabled: true, why: '' },
  { key: 'train', label: '模型训练', to: '/train', enabled: true, why: '' },
  // 位置留在这里而不是排到最后：四页的次序**本身是信息** ——
  // 先看数据、再训模型、再构建场、最后谈影响，与流水线的次序一致。
  { key: 'field', label: '空间温度场的构建', to: '/field', enabled: true, why: '' },
  {
    key: 'impact',
    label: '影响分析',
    to: '/impact',
    enabled: false,
    why: '本轮不做。后端还没有逐点误差与按时段的接口，内容也还没定下来。',
  },
] as const

/**
 * 「断面 / 三维」这两块。**次序是信息**：先切面（快，先让人看懂场），再三维。
 * 两项都开着 —— 三维由 `FieldView` 与实时那一屏各自懒加载，切过去才下载 Three，
 * 所以断面那一边的首屏不为它付钱。
 *
 * 两页共用这一份：实时模式那一屏的两个视图与页③ 是同一件事的两份数据，
 * 文案分两处写迟早会漂成一个叫「三维」一个叫「棚体」。
 */
export const FIELD_VIEWS = [
  { key: 'section', label: '断面', enabled: true, why: '' },
  { key: 'volume', label: '三维', enabled: true, why: '' },
] as const

export type ModeItem = (typeof MODES)[number]
export type NavItem = (typeof NAV_ITEMS)[number]
