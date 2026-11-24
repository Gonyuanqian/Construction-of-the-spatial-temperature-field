import type { Router, RouteLocationNormalized } from 'vue-router'
import type { Account } from '../api/session'
import { homeFor } from '../composables/useAuth'

export function allowed(route: Pick<RouteLocationNormalized, 'meta'>, role: Account['role']): boolean {
  const roles = route.meta.roles as Account['role'][] | undefined
  return !roles || roles.includes(role)
}
export function returnPath(router: Router, candidate: unknown, role: Account['role']): string {
  if (typeof candidate !== 'string' || !/^\/(?!\/)/.test(candidate) || /[\\\u0000-\u001f]/.test(candidate)) return homeFor(role)
  const target = router.resolve(candidate)
  return target.meta.public || !allowed(target, role) || !target.name ? homeFor(role) : target.fullPath
}
