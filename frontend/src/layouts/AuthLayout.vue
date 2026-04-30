<script setup lang="ts">
// Auth layout: centered card, no sidebar
</script>

<template>
  <div class="auth-layout">
    <!-- 装饰性浮动光晕 -->
    <div class="deco deco-1"></div>
    <div class="deco deco-2"></div>
    <div class="deco deco-3"></div>
    <div class="deco deco-4"></div>
    <RouterView />
  </div>
</template>

<style scoped>
.auth-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #e0f2fe 0%, #bae6fd 35%, #e8f4ff 65%, #dbeafe 100%);
  position: relative;
  overflow: hidden;
}

/* 科技网格底纹 */
.auth-layout::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(14, 165, 233, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(14, 165, 233, 0.08) 1px, transparent 1px);
  background-size: 44px 44px;
  pointer-events: none;
}

/* 斜线辅助纹 */
.auth-layout::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(45deg, rgba(56, 189, 248, 0.04) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(56, 189, 248, 0.04) 25%, transparent 25%);
  background-size: 88px 88px;
  pointer-events: none;
}

.deco {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
  animation: float 10s ease-in-out infinite;
}

.deco-1 {
  width: 480px;
  height: 480px;
  background: radial-gradient(circle at 40% 40%, rgba(14, 165, 233, 0.22), transparent 70%);
  top: -160px;
  right: -160px;
  animation-delay: 0s;
}

.deco-2 {
  width: 380px;
  height: 380px;
  background: radial-gradient(circle at 60% 60%, rgba(56, 189, 248, 0.18), transparent 70%);
  bottom: -120px;
  left: -120px;
  animation-delay: -4s;
}

.deco-3 {
  width: 220px;
  height: 220px;
  background: radial-gradient(circle at 50% 50%, rgba(2, 132, 199, 0.14), transparent 70%);
  top: 28%;
  left: 8%;
  animation-delay: -7s;
}

.deco-4 {
  width: 160px;
  height: 160px;
  background: radial-gradient(circle at 50% 50%, rgba(125, 211, 252, 0.2), transparent 70%);
  bottom: 18%;
  right: 12%;
  animation-delay: -2s;
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33%       { transform: translate(18px, -24px) scale(1.06); }
  66%       { transform: translate(-12px, 12px) scale(0.94); }
}
</style>
