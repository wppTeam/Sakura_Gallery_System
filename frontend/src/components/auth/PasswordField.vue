<template>
  <div class="pwd-field">
    <n-input
      :value="modelValue"
      :type="revealed ? 'text' : 'password'"
      :disabled="disabled"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      size="large"
      :status="error ? 'error' : undefined"
      @update:value="onInput"
      @focus="focused = true"
      @blur="onBlur"
      @keydown="detectCaps"
      @keyup="detectCaps"
      @keydown.enter.prevent="$emit('submit')"
    >
      <template #suffix>
        <button
          class="pwd-eye"
          type="button"
          :aria-label="revealed ? '隐藏密码' : '显示密码'"
          :aria-pressed="revealed"
          tabindex="-1"
          @mousedown.prevent
          @click="revealed = !revealed"
        >
          <svg v-if="!revealed" width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M2.2 10S4.9 4.9 10 4.9 17.8 10 17.8 10 15.1 15.1 10 15.1 2.2 10 2.2 10Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
            <circle cx="10" cy="10" r="2.4" stroke="currentColor" stroke-width="1.5" />
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M2.2 10S4.9 4.9 10 4.9 17.8 10 17.8 10 15.1 15.1 10 15.1 2.2 10 2.2 10Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
            <path d="m3.4 3.4 13.2 13.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </button>
      </template>
    </n-input>

    <p v-if="capsOn" class="pwd-caps" aria-live="polite">
      <svg width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M5.5 8.6 10 4.4l4.5 4.2M5.5 14.6h9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      Caps Lock 已开启
    </p>

    <p v-if="error" class="pwd-error">{{ error }}</p>

    <div v-if="showMeter && modelValue" class="pwd-meter-wrap">
      <div class="pwd-meter" :data-strength="strength" aria-hidden="true">
        <span v-for="index in 4" :key="index" class="pwd-meter-seg" :class="{ 'is-on': index <= strength }"></span>
      </div>
      <p class="pwd-meter-label">
        密码强度：<strong>{{ strengthLabel }}</strong>
        <span class="pwd-meter-note">（至少 8 位，含大小写字母和数字）</span>
      </p>
      <ul class="pwd-rules">
        <li v-for="rule in rules" :key="rule.key" :class="{ 'is-ok': rule.ok }">
          <span class="pwd-rule-dot" aria-hidden="true">{{ rule.ok ? '✓' : '·' }}</span>
          {{ rule.label }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    autocomplete?: string
    disabled?: boolean
    showMeter?: boolean
    error?: string
  }>(),
  {
    placeholder: '请输入密码',
    autocomplete: 'current-password',
    disabled: false,
    showMeter: false,
    error: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  submit: []
}>()

const revealed = ref(false)
const capsOn = ref(false)
const focused = ref(false)

const rules = computed(() => [
  { key: 'length', label: '至少 8 位', ok: props.modelValue.length >= 8 },
  { key: 'lower', label: '包含小写字母', ok: /[a-z]/.test(props.modelValue) },
  { key: 'upper', label: '包含大写字母', ok: /[A-Z]/.test(props.modelValue) },
  { key: 'digit', label: '包含数字', ok: /[0-9]/.test(props.modelValue) },
])

const strength = computed(() => rules.value.filter((rule) => rule.ok).length)
const strengthLabel = computed(() => {
  if (strength.value <= 1) return '偏弱'
  if (strength.value === 2) return '一般'
  if (strength.value === 3) return '良好'
  return '很强'
})

function onInput(value: string) {
  emit('update:modelValue', value)
}

function detectCaps(event: KeyboardEvent) {
  // getModifierState 在部分浏览器缺失；两处都读一次，保证 keydown 阶段就能提示
  const keyboardEvent = event as KeyboardEvent
  capsOn.value = keyboardEvent.getModifierState?.('CapsLock') ?? false
}

function onBlur() {
  focused.value = false
  capsOn.value = false
}
</script>

<style scoped>
.pwd-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.pwd-eye {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--faint, #9a8088);
  cursor: pointer;
  transition: color var(--dur-fast, 160ms) var(--ease-out, ease), background var(--dur-fast, 160ms) var(--ease-out, ease);
}
.pwd-eye:hover { color: var(--sakura-deep, #c93a63); background: var(--sakura-wash, rgba(232, 98, 140, 0.08)); }
.pwd-eye:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring, 0 0 0 3px rgba(201, 58, 99, 0.35));
}

.pwd-caps {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-size: var(--fs-xs, 12px);
  color: var(--autumn, #b5703c);
}

.pwd-error {
  margin: 0;
  font-size: var(--fs-xs, 12px);
  color: var(--sakura-deep, #c93a63);
}

.pwd-meter-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 2px;
}

.pwd-meter {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
}
.pwd-meter-seg {
  height: 4px;
  border-radius: 999px;
  background: var(--line, #f3dde5);
  transition: background var(--dur, 240ms) var(--ease-out, ease);
}
.pwd-meter[data-strength='1'] .pwd-meter-seg.is-on { background: #e8a2a2; }
.pwd-meter[data-strength='2'] .pwd-meter-seg.is-on { background: var(--autumn, #b5703c); }
.pwd-meter[data-strength='3'] .pwd-meter-seg.is-on { background: var(--summer, #3b9c80); }
.pwd-meter[data-strength='4'] .pwd-meter-seg.is-on { background: var(--sakura-deep, #c93a63); }

.pwd-meter-label {
  margin: 0;
  font-size: var(--fs-xs, 12px);
  color: var(--muted, #63474f);
}
.pwd-meter-label strong { color: var(--ink, #4a2b35); }
.pwd-meter-note { color: var(--faint, #9a8088); }

.pwd-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.pwd-rules li {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-xs, 12px);
  color: var(--faint, #9a8088);
}
.pwd-rules li.is-ok { color: var(--summer, #3b9c80); }
.pwd-rule-dot { width: 12px; text-align: center; }

@media (prefers-reduced-motion: reduce) {
  .pwd-eye, .pwd-meter-seg { transition: none; }
}
</style>
