import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'chat',
    pathMatch: 'full'
  },
  {
    path: 'chat',
    loadComponent: () => import('./components/chat/chat.component').then(m => m.ChatComponent),
    title: '智能对话'
  },
  {
    path: 'models',
    loadComponent: () => import('./components/models/models.component').then(m => m.ModelsComponent),
    title: '模型配置'
  },
  {
    path: 'import',
    loadComponent: () => import('./components/import/import.component').then(m => m.ImportComponent),
    title: '知识库导入'
  },
  {
    path: 'tasks',
    loadComponent: () => import('./components/tasks/tasks.component').then(m => m.TasksComponent),
    title: '导入任务'
  }
];
