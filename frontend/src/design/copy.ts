/**
 * 全站文案的单一来源。
 *
 * 标题曾由「预测」改为「重建」（spec 2026-10-04 §六 第 6 项）：实时模式按设计是
 * **用当下数据算当下的构场**，不是外推未来，而「未来预测」被明确划在范围外。
 * 当前页面展示名称为「人参棚式空间温度场的监测」。
 * 这个名字同时出现在 copy.ts、index.html 和若干组件里 —— 写死三份就会漂成两个名字，
 * 而验收时看到的正是它。所以有一条测试扫全仓来守。
 */
import type { IconName } from './icons'

export const SYSTEM_TITLE = '人参棚式空间温度场的监测'

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
 * 训练模式左侧导航：数据导入、模型训练、模型库与构场。
 * 模型库紧接训练，便于保存结果后查看和选择构场模型。
 */
export const NAV_ITEMS = [
  { key: 'data', label: '数据导入与检查', to: '/data', enabled: true, why: '', icon: 'upload' },
  { key: 'train', label: '模型训练', to: '/train', enabled: true, why: '', icon: 'chart' },
  { key: 'models', label: '模型库', to: '/models', enabled: true, why: '', icon: 'database' },
  { key: 'field', label: '空间温度场的构建', to: '/field', enabled: true, why: '', icon: 'cube' },
] as const

export const ADMIN_NAV_ITEMS = [
  { key: 'users', label: '用户管理', to: '/admin/users', enabled: true, why: '', icon: 'users' },
  { key: 'greenhouses', label: '棚体档案管理', to: '/admin/greenhouses', enabled: true, why: '', icon: 'cube' },
] as const
export const USER_NAV_ITEMS = [
  { key: 'live', label: '实时监测', to: '/live', enabled: true, why: '', icon: 'pulse' },
  { key: 'greenhouse-design', label: '温室设计', to: '/greenhouse-design', enabled: true, why: '', icon: 'ruler' },
  { key: 'greenhouse-control', label: '温室控制', to: '/greenhouse-control', enabled: true, why: '', icon: 'controls' },
  { key: 'alert-log', label: '预警日志', to: '/alert-log', enabled: true, why: '', icon: 'alert' },
  { key: 'assistant', label: 'AgriSeek', to: '/assistant', enabled: true, why: '', icon: 'chat' },
] as const

/** 管理员通过右上角进入后台，侧栏集中展示开发与管理功能。 */
export const DEVELOPER_NAV_ITEMS = [
  ...NAV_ITEMS,
  ...ADMIN_NAV_ITEMS,
] as const

/**
 * 实时模式那一屏左栏里的四条（2026-10-09 用户裁定三项，2026-10-12 照参考图补成
 * 五项，2026-10-16 精修时合并成四项）。
 *
 * **「首页」并进了「实时监测」**（2026-10-16 用户裁定：「首页就是实时监测，
 * 把这两个合在一起留一个就行」）。合并之后这一屏上终于**有了对象可选** ——
 * 参考图上那个高亮态才落得下来。名字取「实时监测」而不是「首页」：`/`
 * 在这个系统里已经 redirect 到 `/data`（数据导入页），叫「首页」却跳去实时屏，
 * 名实分家。参考图那一条写的是「首页」，此处**有意不照图**。
 *
 * 监测与助手已开放，历史和设置仍保留禁用占位及说明。
 *
 * ⚠️ **不是把 `NAV_ITEMS` 改掉**：训练模式那四页的左栏仍然是流水线那四项，
 * 标签、次序、`enabled` 一个都不动（`App.test.ts` 按 `NAV_ITEMS` 推导着断言）。
 * 这一份只走 `App.vue` → `NavRail` 的 `items`。
 *
 * 「温度场智能助手」预留温度查询、结果解释与视图联动入口，页面接入后再开放。
 *
 * ⚠️ 后三句 `why` 的长度都要大于 10 个字符 —— `guards.test.ts` 有一条守卫
 * 扫「未开放项必带理由」，`LIVE_NAV_ITEMS` 也在它扫的名单里。已开放的那一项
 * 按 `NAV_ITEMS` 的老规矩是空串（它没有「为什么没开」可写）。
 *
 * `icon` 是 `design/icons.ts` 里的名字。训练侧与实时侧都通过这份单一图标表取图。
 */
export const LIVE_NAV_ITEMS = [
  {
    key: 'live', label: '实时监测', to: '/live', enabled: true, icon: 'pulse', why: '',
  },
  {
    key: 'assistant', label: 'AgriSeek', to: '/assistant', enabled: true, icon: 'chat',
    why: '',
  },
  {
    key: 'history', label: '历史数据', to: '/history', enabled: false, icon: 'clock',
    why: '演示屏上留的位置。先把这一屏演示完，再谈回看与追溯。',
  },
  {
    key: 'settings', label: '系统设置', to: '/settings', enabled: false, icon: 'gear',
    why: '演示屏上留的位置。这一屏的控件都在页面上，没有要设的东西。',
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

/**
 * 出处三态。**全站唯一一处**（spec 2026-10-06 §七）。
 *
 * `mark` 是屏上可见的一个字，`why` 是完整那一句 —— 它挂在图章的 `title` 上，
 * 也印在每页「口径与出处」的折叠区里。两个都放这里，是因为图章与折叠区
 * 必须说同一句话；分成两处写，迟早一处改了另一处没改。
 *
 * ⚠️ 屏上原先印的是整句（「随标定包（标定当时算好、写在包里的数）」）——
 * 每个数字后面缀一句括注，通篇如此，于是整页读起来像注释密布的文档
 * （spec §一 成因 6）。降噪不是删掉解释，是把它从正文挪到 `title` 上。
 *
 * ⚠️ 三态说的是**这个数在管线里从哪来**；温度场的分级
 * （实测 / 重建 / 无定义，见 `charts/pick.ts`）说的是**这一格场有没有数**。
 * 两个轴，不许合并、不许互相借字。
 *
 * ⚠️ `mark` 里不许出现被禁字形 —— `routes.smoke.test.ts` 扫得到渲染文本。
 */
export const PROV = {
  pack: { mark: '包', why: '随标定包（标定当时算好、写在包里的数）' },
  live: { mark: '算', why: '现场重算（这次请求现算出来的数）' },
  test: { mark: '测', why: '只有验收测试守（界面上不校验，靠后端测试钉住的数）' },
  // 2026-10-08（模型库）：跑完还没保存的那一份。不加这一档，它和库里那份
  // 在屏上长得一模一样 —— 而「这块数是不是已经留下来了」正是用户此刻
  // 唯一要判断的事。
  unsaved: { mark: '未入库', why: '刚跑完、还没保存到模型库的这一份' },
} as const

/**
 * 空态那一句话。**五个页面共用同一句**（规格书 §六）。
 *
 * 与 `PROV` 同一个理由：五个页面各写一句，迟早漂成五种说法 ——
 * 而用户看到的是「系统有五个地方没数据」，实际只有一件事没做。
 *
 * ⚠️ 这**不是错误文案**：空态是系统的起点。所以这里不出现「错误」「失败」，
 * 也不出现状态码 —— `NoDataset.test.ts` 逐条守着这三样。
 */
export const NO_DATASET = {
  headline: '先导入数据集',
  why: '到「数据导入与检查」那一页选一份 xlsx 导入，这一页的内容都按它算出来。',
} as const

/**
 * 导入块（页① 的第一块，规格书 §五）。**空态下这是全系统唯一可用的一块。**
 *
 * `done` 后面拼出来的整句是规格书定死的形状：
 * 「当前数据集：<文件名>，<N> 个时刻，<起始> 至 <结束>」。
 *
 * ⚠️ `hint` 里**不写 `②③④`**（计划原文写的是它们）：那是规格书自己的页码
 * 记法，屏幕上的读者只有导航栏上那几个页名 —— 本仓别的文案一律按页名称呼
 * 别的页面（`NO_DATASET.why` 说的就是「数据导入与检查」那一页）。一个只在
 * 规格书里存在的记号印到屏上，等于让读者去翻规格书。
 */
export const IMPORT = {
  title: '数据集导入',
  hint: '导入后将更新训练与分析数据。',
  idle: '导入',
  busy: '正在导入…',
  done: '当前数据集',
} as const

/**
 * 模型库（规格书 §六、§七）。
 *
 * 空间验证组使用描述名称，避免与 A/B/C 时间数据集混淆。
 * 不把旧交付数据的背景温度基线数字套用到后来上传的数据。
 */
export const MODELS = {
  title: '模型库',
  entry: '模型库',
  effectHead: '空间留出验证结果',
  listHint: 'R² 需结合相同数据、验证划分与基线一起解读；这些指标不代表跨时段泛化效果。',
  empty: '模型库里还没有模型',
  emptyWhy: '在模型训练页面完成训练并保存，模型会显示在这里。',
  saveTitle: '保存到模型库',
  savePlaceholder: '给这个模型起个名字',
  saveHint: '保存后可在“空间温度场的构建”页面选择此模型，再点击“开始构场”。',
  back: '回模型库',
  view: '查看详情',
  artifactReady: '已保存成品',
  differentSource: '训练来源不同',
  notSolid: '仅保存参数',
  notSolidWhy: '这份记录仅保存参数，构场时可能使用当前数据重新拟合；固定模型评估需先训练并保存成品。',
  /** 保存按钮在忙的那几秒。**说清它会慢** —— 现固化要重训一遍，
   *  十几秒里只写「保存中」，用户只会以为这台机器卡了。 */
  fixating: '正在固化成品',
  fixatingWhy: '要重新训一遍才能固化，可能要十几秒',
} as const

/**
 * 页③ 的选模型块（规格书 §6.4）。页⑤ 的空态也用它。
 *
 * ⚠️ `none` 出现在**一整页什么都没有**的时候 —— 不画断面、不画三维、
 * 不画点选曲线。半画（画了但标一句「用不了」）等于把一个看着对的错场
 * 端给用户（规格书 D4）。
 *
 * ⚠️ 这句理由 2026-10-10 改过一次。原先写的是「要有一个**能对得上当前数据集**
 * 的模型才算得出场」—— 用户裁定「模型不绑数据集」之后，那句话把**一半**的
 * 用法说成了不合法：库里有模型、只是不是为这份数据标的（借来的），照样构得了场
 * （`ModelRowPayload.borrowed`）。现在这一句只说**真正**缺的那样东西：库里
 * 一份都没有。
 */
export const FIELD_MODEL = {
  pick: '用哪个模型',
  placeholder: '请选择用于构场的模型',
  build: '开始构场',
  building: '正在构场…',
  rebuild: '重新构场',
  waiting: '等待开始构场',
  waitingWhy: '请先选择模型，再点击“开始构场”生成温度场。',
  none: '还没有能用的模型',
  noneWhy: '这一页的场要拿模型库里的一份标定过的模型来构 —— 库里现在还没有。',
  toLibrary: '去模型库挑一个',
  toTrain: '去模型训练训一个',
} as const

/**
 * 「借来的」这三个字。**只此一处。**
 *
 * ⚠️ 页③ 选模型那一行的选项、模型库列表里的图章、下面 `calibratedLabel`
 * 那个图章，三处都印它。三处各写一遍不会报错，只会漂 —— 而这三个字正是
 * 用户判断「屏上这些数是不是这份数据的成绩」时唯一的抓手。
 *
 * ⚠️ 它只是**那三个字**。完整的解释是后端 `deps._BORROWED_NOTE` 那一句，
 * 跟着载荷的 `mismatch_note` 到屏上（页③ 与页⑤ 的「口径与出处」里逐字印它）。
 * 前端**不另写一句解释** —— 那就是同一个事实的第二份措辞，正是
 * `deps.py` 里那句注释要挡的事。
 */
export const BORROWED = '借来的'

/**
 * 标定那一个图章的话。**三档，只此一处。**
 *
 * ⚠️ 页③ 的指标卡与图表头、页④ 那一卷、页⑤ 这一帧，四处**都**读它。
 * 四处各写一遍那个三元表达式不会报错，只会漂成「同一个模型，一页说本地的、
 * 一页说借来的」。这是本次最不能错的一处标注：说错了，用户会把一份别人的参数
 * 算出来的误差当成这份数据的成绩。
 *
 * ⚠️ 判「借来的」用的是载荷里那句**话在不在**（`mismatch_note`），不是再比一遍
 * 签名 —— 判据在后端一处（`deps.model_fit`），前端只读结果。
 */
export function calibratedLabel(p: {
  calibrated: boolean
  mismatch_note: string
}): string {
  if (!p.calibrated) return '未标定（兜底参数）'
  return p.mismatch_note ? `已标定（${BORROWED}）` : '已标定'
}

export type ProvKind = keyof typeof PROV

export type ModeItem = (typeof MODES)[number]
export type NavItem = (typeof NAV_ITEMS)[number]

/**
 * 一条导航项。**`NavRail` 的 `items` 收的是它，不是 `NavItem`。**
 *
 * `NavItem` 是 `NAV_ITEMS` 四个字面量的联合（`(typeof NAV_ITEMS)[number]`），
 * `LIVE_NAV_ITEMS` 里一行都套不进去 —— 拿它当属性类型会让那一份传不进来，
 * 而报错落在 `App.vue` 的模板上，离现场很远。
 */
export interface RailItem {
  readonly key: string
  readonly label: string
  readonly to: string
  readonly enabled: boolean
  readonly why: string
  /**
   * `design/icons.ts` 里的图标名。**可选** —— 未提供时导航项可以只显示文字。
   */
  readonly icon?: IconName
}
