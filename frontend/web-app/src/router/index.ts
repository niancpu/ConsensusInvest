import { createRouter, createWebHistory } from 'vue-router'
import WorkflowCreatePage from '../pages/WorkflowCreatePage.vue'
import WorkflowListPage from '../pages/WorkflowListPage.vue'
import WorkflowDetailPage from '../pages/WorkflowDetailPage.vue'
import WorkflowLivePage from '../pages/WorkflowLivePage.vue'
import WorkflowSnapshotPage from '../pages/WorkflowSnapshotPage.vue'
import WorkflowTracePage from '../pages/WorkflowTracePage.vue'
import JudgmentPage from '../pages/JudgmentPage.vue'
import EvidenceDetailPage from '../pages/EvidenceDetailPage.vue'
import AgentArgumentDetailPage from '../pages/AgentArgumentDetailPage.vue'
import EntityEvidencePage from '../pages/EntityEvidencePage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/workflows',
    },
    {
      path: '/workflows',
      name: 'workflow-list',
      component: WorkflowListPage,
    },
    {
      path: '/workflow/new',
      name: 'workflow-new',
      component: WorkflowCreatePage,
    },
    {
      path: '/workflow/:workflowRunId',
      name: 'workflow-detail',
      component: WorkflowDetailPage,
    },
    {
      path: '/workflow/:workflowRunId/live',
      name: 'workflow-live',
      component: WorkflowLivePage,
    },
    {
      path: '/workflow/:workflowRunId/snapshot',
      name: 'workflow-snapshot',
      component: WorkflowSnapshotPage,
    },
    {
      path: '/workflow/:workflowRunId/trace',
      name: 'workflow-trace',
      component: WorkflowTracePage,
    },
    {
      path: '/workflow/:workflowRunId/judgment',
      name: 'workflow-judgment',
      component: JudgmentPage,
    },
    {
      path: '/evidence/:evidenceId',
      name: 'evidence-detail',
      component: EvidenceDetailPage,
    },
    {
      path: '/agent-arguments/:agentArgumentId',
      name: 'agent-argument-detail',
      component: AgentArgumentDetailPage,
    },
    {
      path: '/entities/:entityId/evidence',
      name: 'entity-evidence',
      component: EntityEvidencePage,
    },
  ],
})
