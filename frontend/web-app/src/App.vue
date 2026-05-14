<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="brand-kicker">ConsensusInvest</p>
        <p class="brand-title">可审计工作流控制台</p>
      </div>
      <nav class="topnav">
        <RouterLink to="/workflows">工作流历史</RouterLink>
        <RouterLink to="/workflow/new">新建工作流</RouterLink>
        <RouterLink to="/entities/ent_industry_bank/evidence">实体证据</RouterLink>
      </nav>
    </header>

    <main class="main-content">
      <RouterView v-slot="{ Component }">
        <Transition name="page-fade-slide" mode="out-in" appear>
          <div :key="route.fullPath" class="route-page-shell">
            <component :is="Component" />
          </div>
        </Transition>
      </RouterView>
    </main>
  </div>
</template>
