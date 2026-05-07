<template>
  <div class="screen-shell">
    <RouterView />
  </div>
</template>

<style>
/* 用 fixed 将大屏锁死在视口内，任何子元素溢出都不可滑动 */
.screen-shell {
  position: fixed;
  inset: 0;
  overflow: hidden;
  width: 100vw;
  height: 100dvh;
}
</style>
