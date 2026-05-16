import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    CommonModule
  ],
  template: `
    <div class="app-container">
      <!-- 侧边导航栏 -->
      <nav class="sidebar">
        <div class="sidebar-logo">
          <i class="fa-solid fa-cube"></i>
          <span>知识仓库 Agent</span>
        </div>
        <ul class="menu-list">
          <li>
            <a routerLink="/chat" routerLinkActive="active" class="menu-item">
              <i class="fa-regular fa-comment-dots"></i>
              <span>智能对话</span>
            </a>
          </li>
          <li>
            <a routerLink="/import" routerLinkActive="active" class="menu-item">
              <i class="fa-solid fa-folder-plus"></i>
              <span>知识库导入</span>
            </a>
          </li>
          <li>
            <a routerLink="/tasks" routerLinkActive="active" class="menu-item">
              <i class="fa-regular fa-list-alt"></i>
              <span>导入任务</span>
            </a>
          </li>
          <li>
            <a routerLink="/models" routerLinkActive="active" class="menu-item">
              <i class="fa-solid fa-sliders"></i>
              <span>模型配置</span>
            </a>
          </li>
        </ul>
      </nav>

      <!-- 主内容区 -->
      <main class="main-container">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: [`
    :host {
      display: block;
      height: 100vh;
    }

    .app-container {
      display: flex;
      height: 100vh;
      overflow: hidden;
      background-color: #f6f8fa;
    }

    /* 侧边导航栏 */
    .sidebar {
      width: 220px;
      background: #ffffff;
      border-right: 1px solid #d9d9d9;
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }

    .sidebar-logo {
      height: 56px;
      display: flex;
      align-items: center;
      padding: 0 20px;
      font-size: 15px;
      font-weight: 600;
      color: #1f1f1f;
      border-bottom: 1px solid #f0f0f0;
      gap: 10px;
    }

    .sidebar-logo i {
      color: #0061ff;
      font-size: 20px;
    }

    .menu-list {
      list-style: none;
      padding: 12px 8px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin: 0;
    }

    .menu-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 16px;
      color: #434343;
      text-decoration: none;
      border-radius: 6px;
      font-weight: 400;
      transition: all 0.2s;
      cursor: pointer;
    }

    .menu-item:hover {
      background-color: #f5f5f5;
      color: #1f1f1f;
    }

    .menu-item.active {
      background-color: #e6f0ff;
      color: #0061ff;
      font-weight: 600;
    }

    .menu-item i {
      width: 16px;
      text-align: center;
    }

    /* 主内容区 */
    .main-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background-color: #f0f2f5;
    }
  `]
})
export class AppComponent {
  title = 'knowledge-base-frontend';
}
