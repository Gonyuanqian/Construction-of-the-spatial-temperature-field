import type { Component } from 'vue'
import {
  createRouter, createWebHistory, type Router, type RouterHistory,
} from 'vue-router'

import { NAV_ITEMS } from '../design/copy'
import { homeFor, useAuth } from '../composables/useAuth'
import { allowed } from './access'
import DataView from '../views/DataView.vue'
import FieldView from '../views/FieldView.vue'
import ModelsView from '../views/ModelsView.vue'
import TrainView from '../views/TrainView.vue'

/**
 * 视图表。**静态 import，不用动态 `import()`。**
 *
 * 想用 `() => import(`../views/${name}.vue`)` 的话：Vite 要求 import 的路径
 * **静态可分析**，模板字符串要么让打包器把整个 `views/` 塞进产物，
 * 要么加 `@vite-ignore` —— 而那会让它在运行时去取一个没被编译过的 `.vue`，
 * 构建能过、页面白屏。两页而已，直接引进来最省事。
 */
const VIEWS: Record<string, Component> = {
  data: DataView, train: TrainView, models: ModelsView, field: FieldView,
}

/**
 * 只注册导航里 enabled 的那些页。
 *
 * 未开放的页**不注册路由** —— 一个跳过去只有一句「本轮不做」的页面，
 * 比导航上一个禁用的按钮更难看（spec 2026-10-04 §二.4）。
 * 有一条测试拿 `NAV_ITEMS[i].enabled` 与路由表对账，所以这两处不会各说各话。
 */
export function createAppRouter(history?: RouterHistory): Router {
  const routes = NAV_ITEMS.filter((i) => i.enabled && i.key in VIEWS).map((i) => ({
    path: i.to,
    name: i.key,
    component: VIEWS[i.key],
    meta: { roles: ['ADMIN'], workspace: 'developer' },
  }))

  const router = createRouter({
    history: history ?? createWebHistory(),
    routes: [
      ...routes,
      // 所有角色共用用户视图，训练和开发工具通过独立管理员路由开放。
      {
        path: '/live',
        name: 'live',
        // 懒加载：实时模式那一屏（含三维）不该进首屏。
        component: () => import('../views/LiveView.vue'),
        meta: { roles: ['ADMIN', 'USER'], workspace: 'user', theme: 'live' },
      },
      // 列表路由由训练导航生成；详情沿用同一个工作台组件。
      { path: '/models/:id', name: 'model-detail', component: ModelsView, meta: { roles: ['ADMIN'], workspace: 'developer' } },
      { path: '/replay', redirect: '/live' },
      { path: '/developer/live', redirect: '/live' },
      { path: '/assistant', name: 'assistant', component: () => import('../views/AssistantView.vue'), meta: { roles: ['ADMIN', 'USER'], workspace: 'user', theme: 'live' } },
      { path: '/greenhouse-design', name: 'greenhouse-design', component: () => import('../views/GreenhouseDesignView.vue'), meta: { roles: ['ADMIN', 'USER'], workspace: 'user', theme: 'live' } },
      { path: '/greenhouse-control', name: 'greenhouse-control', component: () => import('../views/GreenhouseControlView.vue'), meta: { roles: ['ADMIN', 'USER'], workspace: 'user', theme: 'live' } },
      { path: '/alert-log', name: 'alert-log', component: () => import('../views/AlertLogView.vue'), meta: { roles: ['ADMIN', 'USER'], workspace: 'user', theme: 'live' } },
      { path: '/assistant/field/:snapshotId', name: 'assistant-field', component: () => import('../views/AssistantFieldView.vue'), meta: { roles: ['ADMIN', 'USER'], workspace: 'user', theme: 'live' } },
      { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
      { path: '/account', name: 'account', component: () => import('../views/AccountView.vue'), meta: { roles: ['ADMIN', 'USER'], workspace: 'user' } },
      { path: '/admin/users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { roles: ['ADMIN'], workspace: 'developer' } },
      { path: '/admin/greenhouses', name: 'greenhouses', component: () => import('../views/GreenhousesView.vue'), meta: { roles: ['ADMIN'], workspace: 'developer' } },
      { path: '/monitor', redirect: '/live' },
      // 系统首页和未知地址统一回到用户视图。
      { path: '/', redirect: '/live' },
      { path: '/:rest(.*)*', redirect: '/live' },
    ],
  })
  router.beforeEach(async to => {
    const auth = useAuth()
    if (!auth.user.value && auth.token.value && auth.phase.value !== 'error') await auth.restore()
    if (to.meta.public) return auth.user.value ? homeFor(auth.user.value.role) : true
    const account = auth.user.value
    if (!account) return { path: '/login', query: { redirect: to.fullPath } }
    if (!allowed(to, account.role)) return homeFor(account.role)
    return true
  })
  return router
}

export default createAppRouter()
