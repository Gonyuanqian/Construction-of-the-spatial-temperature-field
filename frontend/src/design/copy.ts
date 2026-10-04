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
 * 顶部模式开关的两项。实时模式本轮只是把**位置**定下来：
 * 它要扩后端库并重跑标定（spec 2026-10-04 §三.1），排在训练模式之后。
 */
export const MODES = [
  { key: 'train', label: '训练模式', enabled: true, why: '' },
  {
    key: 'live',
    label: '实时模式',
    enabled: false,
    why: '排在后面：它要先扩后端库、并把留出的那一段重新标定一次，训练模式这几页一行都不需要。',
  },
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
  {
    key: 'field',
    label: '空间温度场的构建',
    to: '/field',
    enabled: false,
    why: '排在下一份计划里：它要先有后端的管线缓存、切面与三维体积接口。位置留在这里，因为四页的次序本身是信息。',
  },
  {
    key: 'impact',
    label: '影响分析',
    to: '/impact',
    enabled: false,
    why: '本轮不做。后端还没有逐点误差与按时段的接口，内容也还没定下来。',
  },
] as const

/**
 * 页③ 的两种视图。**次序是信息**：先切面（快，先让人看懂场），再三维
 * （spec 2026-10-04 §2.3）。未开放的那一项必须带一句给人看的理由 ——
 * 与 `MODES` / `NAV_ITEMS` 同一条规矩，`guards.test.ts` 一起管着。
 */
export const FIELD_VIEWS = [
  { key: 'section', label: '断面', enabled: true, why: '' },
  {
    key: 'volume',
    label: '三维',
    enabled: false,
    why: '排在下一份计划（V7 棚体三维场）：它要先有后端的体积接口，以及 Three.js。' +
      '先做切面，是因为一张二维的场已经能回答"这片场长什么样"。',
  },
] as const

export type ModeItem = (typeof MODES)[number]
export type NavItem = (typeof NAV_ITEMS)[number]
