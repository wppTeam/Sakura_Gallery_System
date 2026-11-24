<template>
  <form
    class="search-bar"
    :class="[`search-bar--${size}`, { 'is-busy': busy }]"
    role="search"
    @submit.prevent="submit"
  >
    <label :for="inputId" class="sr-only">{{ label }}</label>
    <svg class="search-icon" width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="8.8" cy="8.8" r="5.6" stroke="currentColor" stroke-width="1.6" />
      <path d="m13.2 13.2 3.4 3.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
    </svg>
    <input
      :id="inputId"
      v-model="value"
      class="search-input"
      type="search"
      :placeholder="placeholder"
      :autocomplete="'off'"
      enterkeyhint="search"
    />
    <button type="submit" class="search-btn" :disabled="busy">
      {{ buttonText }}
    </button>
  </form>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    placeholder?: string
    label?: string
    size?: 'md' | 'lg'
    buttonText?: string
    busy?: boolean
  }>(),
  {
    modelValue: '',
    placeholder: '搜索作品、标题或标签',
    label: '搜索',
    size: 'md',
    buttonText: '搜索',
    busy: false,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'submit', value: string): void
}>()

const value = ref(props.modelValue)
const inputId = computed(() => `search-${Math.random().toString(36).slice(2, 9)}`)

watch(
  () => props.modelValue,
  (next) => {
    if (next !== value.value) value.value = next
  },
)

watch(value, (next) => emit('update:modelValue', next))

function submit() {
  emit('submit', value.value.trim())
}
</script>

<style scoped>
.search-bar {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-pill);
  background: var(--surface);
  transition: border-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}

.search-bar:focus-within {
  border-color: var(--sakura);
  box-shadow: var(--focus-ring);
}

.search-icon {
  flex-shrink: 0;
  margin-inline: 18px 10px;
  color: var(--faint);
}

.search-input {
  min-width: 0;
  flex: 1;
  height: 100%;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font-size: var(--fs-14);
}

.search-input::placeholder {
  color: var(--faint);
}

.search-input::-webkit-search-cancel-button {
  appearance: none;
}

.search-btn {
  flex-shrink: 0;
  margin: 5px;
  height: calc(100% - 10px);
  padding: 0 22px;
  border-radius: var(--r-pill);
  background: var(--sakura-deep);
  color: var(--on-accent);
  font-size: var(--fs-14);
  font-weight: 500;
  transition: background-color var(--dur-fast) var(--ease-out);
}

.search-btn:hover {
  background: var(--sakura-deep-hover);
}

.search-btn:disabled {
  opacity: 0.7;
}

/* md：顶栏用 */
.search-bar--md {
  height: 42px;
}

.search-bar--md .search-icon {
  width: 16px;
  height: 16px;
  margin-inline: 15px 8px;
}

.search-bar--md .search-btn {
  padding: 0 16px;
  font-size: var(--fs-13, 13px);
}

/* lg：首屏用 */
.search-bar--lg {
  height: 62px;
  border-color: rgba(236, 205, 216, 0.9);
  box-shadow: var(--shadow-soft);
}

.search-bar--lg .search-icon {
  width: 21px;
  height: 21px;
  margin-inline: 22px 12px;
}

.search-bar--lg .search-input {
  font-size: var(--fs-16);
}

.search-bar--lg .search-btn {
  height: calc(100% - 12px);
  margin: 6px;
  padding: 0 30px;
  font-size: var(--fs-16);
}

@media (max-width: 560px) {
  .search-bar--lg {
    height: 56px;
  }

  .search-bar--lg .search-btn {
    padding: 0 20px;
  }
}
</style>
