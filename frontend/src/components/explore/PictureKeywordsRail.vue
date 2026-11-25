<template>
  <section v-if="loading || keywords.length" class="kw-rail" aria-labelledby="kw-title">
    <div class="kw-head">
      <h2 id="kw-title" class="kw-title">画面关键词</h2>
      <p class="kw-hint">来自作品标签 · 点一个看看同类画面</p>
    </div>

    <div v-if="loading" class="kw-track kw-track--loading" aria-hidden="true">
      <span v-for="index in 8" :key="index" class="kw-skeleton" />
    </div>

    <div v-else class="kw-track" role="list">
      <button
        v-for="keyword in keywords"
        :key="keyword.name"
        type="button"
        class="kw-chip"
        role="listitem"
        @click="goSearch(keyword.name)"
      >
        <span class="kw-name">{{ keyword.name }}</span>
        <span v-if="keyword.count > 0" class="kw-count">{{ keyword.count }}</span>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchPublicPopularTags, type PublicTagCount } from '../../api/public'

const MAX_KEYWORDS = 12

const router = useRouter()
const keywords = ref<PublicTagCount[]>([])
const loading = ref(true)

/** 失败/为空时 keywords 保持空数组，整块静默隐藏，不影响首屏与筛选 */
async function loadKeywords() {
  try {
    const items = await fetchPublicPopularTags(MAX_KEYWORDS)
    keywords.value = items.slice(0, MAX_KEYWORDS)
  } catch {
    keywords.value = []
  } finally {
    loading.value = false
  }
}

function goSearch(name: string) {
  const keyword = name.trim()
  if (!keyword) return
  void router.push({ path: '/search', query: { q: keyword, mode: 'fast' } })
}

onMounted(loadKeywords)
</script>

<style scoped>
.kw-rail {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 18px 0 2px;
}

.kw-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
}

.kw-title {
  margin: 0;
  font-family: var(--display, inherit);
  font-size: 16px;
  line-height: 1.5;
  font-weight: 700;
  color: var(--ink, #4a2b35);
  letter-spacing: 0.01em;
}

.kw-hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--faint, #9a8590);
}

/* 单行横向滚动；滚动条隐藏，键盘仍可 Tab 聚焦 */
.kw-track {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 2px 1px 6px;
  scrollbar-width: none;
  -ms-overflow-style: none;
  -webkit-overflow-scrolling: touch;
}

.kw-track::-webkit-scrollbar {
  display: none;
}

.kw-track--loading {
  overflow: hidden;
}

.kw-chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 5px 13px;
  border: 1px solid var(--line, rgba(201, 58, 99, 0.16));
  border-radius: 999px;
  background: var(--surface, #fff);
  color: var(--ink-soft, #63474f);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.4;
  white-space: nowrap;
  cursor: pointer;
  transition: border-color 160ms var(--ease-out, ease), color 160ms var(--ease-out, ease),
    background-color 160ms var(--ease-out, ease);
}

.kw-chip:hover {
  border-color: var(--sakura, #e8628c);
  background: var(--sakura-mist, #ffeef4);
  color: var(--sakura-deep, #c93a63);
}

.kw-chip:focus-visible {
  outline: 3px solid var(--focus-ring, rgba(201, 58, 99, 0.45));
  outline-offset: 2px;
}

.kw-name {
  font-weight: 500;
}

.kw-count {
  font-size: 11px;
  color: var(--faint, #9a8590);
  font-variant-numeric: tabular-nums;
}

.kw-skeleton {
  flex: 0 0 auto;
  width: 86px;
  height: 32px;
  border-radius: 999px;
  background: linear-gradient(
    100deg,
    var(--surface-soft, #fff0f5) 20%,
    var(--sakura-wash, #fff6f9) 40%,
    var(--surface-soft, #fff0f5) 60%
  );
  background-size: 200% 100%;
  animation: kw-shimmer 1.4s ease-in-out infinite;
}

@keyframes kw-shimmer {
  0% {
    background-position: 120% 0;
  }
  100% {
    background-position: -80% 0;
  }
}

@media (max-width: 560px) {
  .kw-rail {
    padding-top: 14px;
  }

  .kw-track {
    gap: 7px;
  }
}

/* 触屏：chips 可点区域 ≥44px */
@media (pointer: coarse) {
  .kw-chip {
    min-height: 44px;
    padding: 9px 15px;
  }

  .kw-skeleton {
    height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .kw-skeleton {
    animation: none;
  }

  .kw-chip {
    transition: none;
  }
}
</style>
