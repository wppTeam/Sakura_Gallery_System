<template>
  <n-modal
    :show="show"
    preset="card"
    :bordered="false"
    class="terms-modal"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <template #header>
      <div class="terms-head">
        <span class="terms-eyebrow">COMMUNITY · 社区规范</span>
        <strong>社区规范与隐私说明</strong>
      </div>
    </template>

    <div class="terms-body">
      <section>
        <h3>一、内容与授权</h3>
        <p>你发布的每一张作品都应是你本人创作或已获得合法授权的素材。默认授权为「保留所有权利」，他人转载、二次创作或商用前需要联系你本人；你可以在作品信息中补充更开放的授权方式。</p>
      </section>
      <section>
        <h3>二、人像与隐私</h3>
        <p>含可识别人物的作品默认为人像作品，公开页展示的是经过模糊与像素化处理的脱敏图；原图仅你本人与站点管理员可见。发布前请确认已获得被摄者同意，涉及图生图、换脸等内容必须额外确认。</p>
      </section>
      <section>
        <h3>三、AI 生成内容</h3>
        <p>按《人工智能生成合成内容标识办法》要求，投稿时必须声明是否包含 AI 生成合成内容。声明为「是」的作品会在详情页显示显式标识，下载副本会写入 XMP 隐式标识，并进入人工复核流程。</p>
      </section>
      <section>
        <h3>四、你的个人信息</h3>
        <p>学号和真实姓名永不对外公开，公开页只展示你设置的公开用户名或昵称。图片中的 GPS 定位会在入库时剥离，公开响应不包含完整 EXIF。我们只收集维持账号与作品发布所必需的信息。</p>
      </section>
      <section>
        <h3>五、审核与申诉</h3>
        <p>作品可能经过规则校验与 Agent 辅助预审，最终发布由人工或社区评审确认。若你认为处理有误，可联系站点管理员说明情况。违规内容会被下架，严重违规可能导致账号被停用。</p>
      </section>
    </div>

    <template #footer>
      <div class="terms-actions">
        <n-button type="primary" @click="emit('update:show', false)">我知道了</n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()
</script>

<style scoped>
.terms-modal {
  width: min(560px, calc(100vw - 32px));
  border-radius: var(--r-card, 20px);
}
.terms-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.terms-eyebrow {
  font-size: var(--fs-xs, 12px);
  font-weight: 600;
  letter-spacing: 0.16em;
  color: var(--sakura-deep, #c93a63);
}
.terms-head strong {
  font-size: 19px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
}
.terms-body {
  max-height: min(56vh, 480px);
  overflow-y: auto;
  padding-right: 6px;
}
.terms-body section + section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--line, #f3dde5);
}
.terms-body h3 {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 700;
  color: var(--ink, #4a2b35);
}
.terms-body p {
  margin: 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--muted, #63474f);
}
.terms-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
