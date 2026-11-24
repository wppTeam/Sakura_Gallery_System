<template>
  <div class="public-shell">
    <a class="skip-link" href="#main">跳到主要内容</a>

    <SiteHeader />

    <main id="main" class="public-main" tabindex="-1">
      <RouterView v-slot="{ Component, route }">
        <Transition name="page" mode="out-in">
          <!--
            详情页在不同作品之间切换时保持同一个组件实例（key 固定），
            这样观展模式的上一张/下一张是原地替换，灯箱不会「关→开」重挂载。
            其它路由仍然按 path 重挂载，保留页面转场。
          -->
          <component :is="Component" :key="route.name === 'PhotoDetail' ? 'photo-detail' : route.path" />
        </Transition>
      </RouterView>
    </main>

    <SiteFooter />

    <Transition name="top">
      <button v-if="showBackTop" class="back-top" type="button" aria-label="回到页面顶部" @click="backToTop">
        <svg width="17" height="17" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M10 16V4m0 0L4.6 9.4M10 4l5.4 5.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterView } from 'vue-router'
import SiteFooter from '../components/layout/SiteFooter.vue'
import SiteHeader from '../components/layout/SiteHeader.vue'

const showBackTop = ref(false)

function onScroll() {
  showBackTop.value = window.scrollY > window.innerHeight * 1.4
}

function backToTop() {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
}

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
})
</script>

<style scoped>
.public-shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: var(--ground);
}

.public-main {
  flex: 1 0 auto;
  padding-top: 0;
}

.public-main:focus {
  outline: none;
}

.back-top {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: var(--z-sticky);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--line-strong);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  color: var(--ink);
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(8px);
  transition: transform var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}

.back-top:hover {
  color: var(--sakura-deep);
  border-color: var(--sakura);
  transform: translateY(-2px);
}

.top-enter-active,
.top-leave-active {
  transition: opacity 180ms var(--ease-out), transform 180ms var(--ease-out);
}

.top-enter-from,
.top-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}

/* 页面切换：只做 240ms 淡入，不做大位移 */
.page-enter-active,
.page-leave-active {
  transition: opacity 240ms var(--ease-out);
}

.page-enter-from,
.page-leave-to {
  opacity: 0;
}

@media (max-width: 720px) {
  .back-top {
    right: 16px;
    bottom: 16px;
    width: 40px;
    height: 40px;
  }
}
</style>
