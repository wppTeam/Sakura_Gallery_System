/**
 * v-reveal：滚动进入视口时加 .is-in（样式见 styles/motion.css）
 *
 * - 单个共享 IntersectionObserver，元素进入一次即取消观察；
 * - prefers-reduced-motion 时直接显示，不做位移；
 * - 支持 `v-reveal="index"` 传延迟序号（--reveal-i）。
 */
import type { Directive } from 'vue'

let observer: IntersectionObserver | null = null

function getObserver(): IntersectionObserver {
  if (observer) return observer
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const el = entry.target as HTMLElement
        el.classList.add('is-in')
        observer?.unobserve(el)
      }
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.08 },
  )
  return observer
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

export const vReveal: Directive<HTMLElement, number | undefined> = {
  mounted(el, binding) {
    el.classList.add('reveal')
    const index = typeof binding.value === 'number' ? binding.value : 0
    if (index > 0) el.style.setProperty('--reveal-i', String(index))
    if (prefersReducedMotion()) {
      el.classList.add('is-in')
      return
    }
    getObserver().observe(el)
  },
  unmounted(el) {
    observer?.unobserve(el)
  },
}
