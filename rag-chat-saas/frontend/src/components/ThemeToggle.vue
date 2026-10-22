<script setup lang="ts">
import { Sun, Moon } from 'lucide-vue-next'
import { theme, toggleTheme } from '../theme'
</script>

<template>
  <button class="icon-button theme-toggle" type="button" :title="theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'" :aria-label="theme === 'dark' ? '切换到日间模式' : '切换到夜间模式'" @click="toggleTheme">
    <Sun v-if="theme === 'dark'" :size="17" aria-hidden="true"/><Moon v-else :size="17" aria-hidden="true"/>
  </button>
</template>
