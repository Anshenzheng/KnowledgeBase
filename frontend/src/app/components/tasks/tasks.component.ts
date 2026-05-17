import { Component, OnInit, OnDestroy, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { provideAnimations } from '@angular/platform-browser/animations';
import { trigger, state, style, transition, animate } from '@angular/animations';
import { MatDialogModule, MatDialog, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { TaskService, TaskStatus, TaskType } from '../../services/task.service';
import { ImportTask } from '../../services/knowledge.service';
import { Subscription, interval } from 'rxjs';
import { switchMap } from 'rxjs/operators';

@Component({
  selector: 'app-tasks',
  standalone: true,
  imports: [CommonModule, FormsModule, MatDialogModule, MatButtonModule],
  providers: [provideAnimations()],
  animations: [
    trigger('expandCollapse', [
      state('collapsed', style({
        height: '0px',
        opacity: '0',
        overflow: 'hidden'
      })),
      state('expanded', style({
        height: '*',
        opacity: '1',
        overflow: 'visible'
      })),
      transition('collapsed <=> expanded', [
        animate('300ms ease-in-out')
      ])
    ])
  ],
  template: `
    <div class="main-header">
      <h1 class="page-title">导入任务</h1>
    </div>

    <div class="content-body">
      <!-- 筛选区 -->
      <section class="filter-bar">
        <div class="filter-item">
          <label>状态筛选</label>
          <select [(ngModel)]="statusFilter" (ngModelChange)="filterByStatus($event)">
            <option value="all">全部状态</option>
            <option value="pending">等待中</option>
            <option value="running">运行中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
          </select>
        </div>
        <div class="filter-item">
          <label>类型筛选</label>
          <select [(ngModel)]="typeFilter" (ngModelChange)="filterByType($event)">
            <option value="all">全部类型</option>
            <option value="web">网页</option>
            <option value="local_file">本地文件</option>
            <option value="video">视频</option>
          </select>
        </div>
        <button class="btn-action-default" (click)="loadTasks()">
          <i class="fa-solid fa-rotate"></i>
          刷新
        </button>
      </section>

      <!-- 表格区 -->
      <section class="table-container" *ngIf="!isLoading && paginatedTasks.length > 0">
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th style="width: 45%;">任务名称</th>
                <th style="width: 15%;">状态</th>
                <th style="width: 22%;">进度</th>
                <th style="width: 18%;">操作</th>
              </tr>
            </thead>
            <tbody>
              <ng-container *ngFor="let task of paginatedTasks">
                <!-- 任务行 -->
                <tr class="task-row" [id]="'task-' + task.id" (click)="toggleExpand(task)" style="cursor: pointer;">
                  <td>
                    <div class="task-column-name">
                      <button class="btn-toggle-expand" (click)="toggleExpand(task); $event.stopPropagation()">
                        <i class="fa-solid" [class.fa-caret-down]="isExpanded(task)" [class.fa-caret-right]="!isExpanded(task)"></i>
                      </button>
                      <div class="task-detail">
                        <div class="task-title">{{ task.task_name }}</div>
                        <div class="task-source">
                          <i class="fa-solid" [class.fa-globe]="task.task_type === 'web'" [class.fa-file]="task.task_type === 'local_file'" [class.fa-video]="task.task_type === 'video'"></i>
                          {{ getTaskTypeName(task.task_type) }}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span class="badge" [class.running]="task.status === 'running'" [class.failed]="task.status === 'failed'" [class.success]="task.status === 'completed'">
                      {{ getStatusName(task.status) }}
                    </span>
                  </td>
                  <td>
                    <div class="cell-progress" *ngIf="task.total_items > 0">
                      <div class="progress-track">
                        <div class="progress-fill" [class.none]="task.status === 'failed'" [style.width.%]="task.progress_percentage"></div>
                      </div>
                      <div class="progress-num">{{ task.processed_items }} / {{ task.total_items }} ({{ task.progress_percentage | number:'1.0-0' }}%)</div>
                    </div>
                    <div class="cell-progress" *ngIf="task.total_items === 0">
                      <div class="progress-track">
                        <div class="progress-fill none" style="width: 0;"></div>
                      </div>
                      <div class="progress-num">-</div>
                    </div>
                  </td>
                  <td>
                    <div class="operation-group">
                      <button class="btn-link-action" *ngIf="task.status === 'running'" (click)="cancelTask(task); $event.stopPropagation()" title="取消任务">
                        <i class="fa-solid fa-pause"></i>
                      </button>
                      <button class="btn-link-action" *ngIf="task.status === 'failed'" (click)="viewTaskDetail(task); $event.stopPropagation()" title="查看错误" style="color: var(--status-red);">
                        <i class="fa-solid fa-bug"></i>
                      </button>
                      <button class="btn-link-action" (click)="viewTaskDetail(task); $event.stopPropagation()" title="详情">
                        <i class="fa-solid fa-circle-info"></i>
                      </button>
                      <button class="btn-link-action" (click)="deleteTask(task); $event.stopPropagation()" title="删除">
                        <i class="fa-regular fa-trash-can"></i>
                      </button>
                    </div>
                  </td>
                </tr>
                
                <!-- 展开详情行 -->
                <tr *ngIf="isExpanded(task)" class="detail-row-container" [id]="'detail-' + task.id">
                  <td colspan="4">
                    <div class="detail-wrapper" [@expandCollapse]="isExpanded(task) ? 'expanded' : 'collapsed'">
                      <div class="detail-content">
                        <div class="detail-row">
                          <strong>任务 ID:</strong>
                          <span>{{ task.id }}</span>
                        </div>
                        <div class="detail-row">
                          <strong>创建时间:</strong>
                          <span>{{ task.created_at | date:'yyyy-MM-dd HH:mm:ss' }}</span>
                        </div>
                        <div class="detail-row" *ngIf="task.started_at">
                          <strong>开始时间:</strong>
                          <span>{{ task.started_at | date:'yyyy-MM-dd HH:mm:ss' }}</span>
                        </div>
                        <div class="detail-row" *ngIf="task.completed_at">
                          <strong>完成时间:</strong>
                          <span>{{ task.completed_at | date:'yyyy-MM-dd HH:mm:ss' }}</span>
                        </div>
                        <div class="detail-row" *ngIf="task.input_url">
                          <strong>源 URL:</strong>
                          <span>{{ task.input_url }}</span>
                        </div>
                        <div class="detail-row" *ngIf="task.input_path">
                          <strong>源路径:</strong>
                          <span>{{ task.input_path }}</span>
                        </div>
                        <div class="detail-row" *ngIf="task.error_message">
                          <strong>错误信息:</strong>
                          <span class="error-message">{{ task.error_message }}</span>
                        </div>
                        <div class="detail-row" *ngIf="task.failed_items > 0">
                          <strong>失败数量:</strong>
                          <span class="error-message">{{ task.failed_items }}</span>
                        </div>
                        
                        <!-- 执行日志按钮 -->
                        <div class="task-logs-action" *ngIf="task.log_count && task.log_count > 0">
                          <button class="btn-action-default" (click)="openLogsDialog(task); $event.stopPropagation()">
                            <i class="fa-solid fa-list-ul"></i>
                            查看执行日志 ({{ task.log_count }})
                          </button>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </ng-container>
            </tbody>
          </table>
        </div>
        
        <!-- 分页控件 -->
        <div class="pagination-container" *ngIf="totalPages > 1">
          <div class="pagination-info">
            显示 {{ startIndex + 1 }} - {{ endIndex }} 条，共 {{ filteredTasks.length }} 条
          </div>
          <div class="pagination-controls">
            <button class="btn-page" [disabled]="currentPage === 0" (click)="changePage(currentPage - 1)">
              <i class="fa-solid fa-chevron-left"></i>
            </button>
            <button class="btn-page" 
                    *ngFor="let page of pageNumbers" 
                    [class.active]="page === currentPage"
                    (click)="changePage(page)">
              {{ page + 1 }}
            </button>
            <button class="btn-page" [disabled]="currentPage === totalPages - 1" (click)="changePage(currentPage + 1)">
              <i class="fa-solid fa-chevron-right"></i>
            </button>
          </div>
        </div>
      </section>

      <!-- 空状态 -->
      <div *ngIf="!isLoading && filteredTasks.length === 0" class="empty-state">
        <i class="fa-regular fa-folder-open"></i>
        <h3>暂无任务</h3>
        <p>在"知识库导入"页面创建导入任务</p>
      </div>

      <!-- 加载状态 -->
      <div *ngIf="isLoading" class="loading-container">
        <i class="fa-solid fa-circle-notch fa-spin"></i>
        <p>正在加载任务列表...</p>
      </div>
    </div>
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }

    .main-header {
      flex-shrink: 0;
      height: 56px;
      background: #ffffff;
      border-bottom: 1px solid #f0f0f0;
      display: flex;
      align-items: center;
      padding: 0 24px;
    }

    .page-title {
      font-size: 16px;
      font-weight: 600;
      color: #1f1f1f;
    }

    .content-body {
      flex: 1;
      min-height: 0;
      padding: 24px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    /* 筛选区 */
    .filter-bar {
      background: #ffffff;
      padding: 16px;
      border-radius: 6px;
      border: 1px solid #f0f0f0;
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .filter-item {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .filter-item label {
      font-size: 13px;
      color: #8c8c8c;
      white-space: nowrap;
    }

    .filter-item select {
      height: 32px;
      min-width: 140px;
      padding: 0 10px;
      border-radius: 4px;
      border: 1px solid #d9d9d9;
      background-color: #fff;
      color: #434343;
      outline: none;
      font-size: 14px;
    }

    .filter-item select:focus {
      border-color: #1677ff;
    }

    .btn-action-default {
      height: 32px;
      padding: 0 16px;
      background: #ffffff;
      border: 1px solid #d9d9d9;
      border-radius: 4px;
      color: #434343;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      transition: all 0.2s;
    }

    .btn-action-default:hover {
      color: #1677ff;
      border-color: #1677ff;
    }

    /* 表格区 */
    .table-container {
      background: #ffffff;
      border-radius: 6px;
      border: 1px solid #f0f0f0;
      overflow: hidden;
    }

    .table-responsive {
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      table-layout: fixed;
    }

    th {
      background: #fafafa;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 500;
      color: #1f1f1f;
      border-bottom: 1px solid #d9d9d9;
    }

    td {
      padding: 12px 16px;
      border-bottom: 1px solid #f0f0f0;
      font-size: 14px;
      word-break: break-all;
      white-space: normal;
    }

    tr:hover td {
      background-color: #fafafa;
    }

    /* 任务名称列 */
    .task-column-name {
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .btn-toggle-expand {
      background: none;
      border: none;
      color: #8c8c8c;
      cursor: pointer;
      padding-top: 2px;
    }

    .btn-toggle-expand:hover {
      color: #1f1f1f;
    }

    .task-detail {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .task-title {
      color: #1f1f1f;
      font-weight: 400;
      line-height: 1.5;
    }

    .task-source {
      font-size: 12px;
      color: #8c8c8c;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    /* 状态标签 */
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      font-size: 12px;
      border-radius: 4px;
      font-weight: 400;
      border: 1px solid transparent;
    }

    .badge.running {
      color: #0958d9;
      background-color: #e6f4ff;
      border-color: #91caee;
    }

    .badge.failed {
      color: #cf1322;
      background-color: #fff1f0;
      border-color: #ffa39e;
    }

    .badge.success {
      color: #389e0d;
      background-color: #f6ffed;
      border-color: #b7eb8f;
    }

    /* 进度条 */
    .cell-progress {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .progress-track {
      flex: 1;
      height: 6px;
      background-color: #f5f5f5;
      border-radius: 100px;
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      background-color: #1677ff;
      border-radius: 100px;
    }

    .progress-fill.none {
      background-color: #d9d9d9;
    }

    .progress-num {
      font-size: 12px;
      color: #8c8c8c;
      min-width: 120px;
      text-align: right;
    }

    /* 操作按钮组 */
    .operation-group {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .btn-link-action {
      background: none;
      border: none;
      color: #1677ff;
      cursor: pointer;
      font-size: 14px;
      padding: 0;
      transition: color 0.2s;
    }

    .btn-link-action:hover {
      color: #4096ff;
    }

    /* 空状态和加载状态 */
    .empty-state, .loading-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 60px 20px;
      background: #ffffff;
      border-radius: 6px;
      border: 1px solid #f0f0f0;
    }

    .empty-state i, .loading-container i {
      font-size: 48px;
      color: #d9d9d9;
      margin-bottom: 16px;
    }

    .empty-state h3, .loading-container p {
      font-size: 16px;
      color: #1f1f1f;
      margin-bottom: 8px;
    }

    .empty-state p {
      font-size: 14px;
      color: #8c8c8c;
    }

    .loading-container i {
      color: #1677ff;
    }

    /* 展开详情行 */
    .detail-row-container td {
      padding: 0;
      border-bottom: 1px solid #f0f0f0;
      background-color: #fafafa;
    }

    .detail-wrapper {
      overflow-x: visible;
      overflow-y: auto;
      max-height: min(60vh, 500px);
    }

    .detail-content {
      padding: 16px 24px;
      display: grid;
      gap: 12px;
    }

    .detail-row {
      display: flex;
      gap: 16px;
      font-size: 13px;
    }

    .detail-row strong {
      min-width: 100px;
      color: #434343;
      font-weight: 500;
    }

    .detail-row span {
      color: #8c8c8c;
      flex: 1;
      word-break: break-all;
    }

    .detail-row .error-message {
      color: var(--status-red);
      font-family: monospace;
      background-color: var(--status-red-bg);
      padding: 8px 12px;
      border-radius: 4px;
      display: block;
      margin-top: 4px;
      max-height: 200px;
      overflow-y: auto;
    }

    /* 任务日志 */
    .task-logs {
      margin-top: 20px;
      border-top: 1px solid #f0f0f0;
      padding-top: 16px;
    }

    .logs-title {
      font-size: 14px;
      font-weight: 600;
      color: #1f1f1f;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .logs-title i {
      color: #1677ff;
    }

    .logs-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 400px;
      overflow-y: auto;
      background-color: #fafafa;
      border-radius: 4px;
      padding: 12px;
    }

    .log-entry {
      padding: 10px 12px;
      border-radius: 4px;
      border-left: 3px solid transparent;
      background-color: #fff;
    }

    .log-entry.log-info {
      border-left-color: #1677ff;
      background-color: #e6f4ff;
    }

    .log-entry.log-success {
      border-left-color: #389e0d;
      background-color: #f6ffed;
    }

    .log-entry.log-warning {
      border-left-color: #faad14;
      background-color: #fffbe6;
    }

    .log-entry.log-error {
      border-left-color: #cf1322;
      background-color: #fff1f0;
    }

    .log-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
    }

    .log-time {
      font-size: 12px;
      color: #8c8c8c;
      font-family: monospace;
    }

    .log-level-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
    }

    .log-level-badge.badge-info {
      background-color: #1677ff;
      color: #fff;
    }

    .log-level-badge.badge-success {
      background-color: #389e0d;
      color: #fff;
    }

    .log-level-badge.badge-warning {
      background-color: #faad14;
      color: #fff;
    }

    .log-level-badge.badge-error {
      background-color: #cf1322;
      color: #fff;
    }

    .log-message {
      font-size: 13px;
      color: #1f1f1f;
      line-height: 1.5;
    }

    .log-detail {
      margin-top: 6px;
      font-size: 12px;
      color: #434343;
      font-family: monospace;
      background-color: rgba(0, 0, 0, 0.05);
      padding: 6px 8px;
      border-radius: 4px;
      overflow-x: auto;
    }

    /* 分页控件 */
    .pagination-container {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 24px;
      background-color: #fafafa;
      border-top: 1px solid #f0f0f0;
    }

    .pagination-info {
      font-size: 13px;
      color: #8c8c8c;
    }

    .pagination-controls {
      display: flex;
      gap: 8px;
    }

    .btn-page {
      min-width: 32px;
      height: 32px;
      padding: 0 8px;
      border: 1px solid #d9d9d9;
      background-color: #fff;
      border-radius: 4px;
      color: #434343;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    .btn-page:hover:not(:disabled) {
      color: #1677ff;
      border-color: #1677ff;
    }

    .btn-page.active {
      color: #fff;
      background-color: #1677ff;
      border-color: #1677ff;
    }

    .btn-page:disabled {
      color: #d9d9d9;
      cursor: not-allowed;
    }

    /* 修复日志容器滚动问题 */
    .logs-container {
      background: #fff;
      border: 1px solid #e8e8e8;
      border-radius: 4px;
      padding: 12px;
    }

    /* 详情区域滚动条样式 */
    .detail-wrapper::-webkit-scrollbar {
      width: 8px;
    }

    .detail-wrapper::-webkit-scrollbar-thumb {
      background-color: #c1c1c1;
      border-radius: 4px;
    }

    .detail-wrapper::-webkit-scrollbar-track {
      background-color: #f0f0f0;
    }
  `]
})
export class TasksComponent implements OnInit, OnDestroy {
  tasks: ImportTask[] = [];
  isLoading = true;
  statusFilter: TaskStatus | 'all' = 'all';
  typeFilter: TaskType | 'all' = 'all';
  expandedTaskId: string | null = null;
  
  // 分页相关
  pageSize = 10;
  currentPage = 0;
  
  private refreshSubscription?: Subscription;

  constructor(
    private taskService: TaskService,
    private dialog: MatDialog
  ) { }

  ngOnInit(): void {
    this.loadTasks();
    this.startAutoRefresh();
  }

  ngOnDestroy(): void {
    this.refreshSubscription?.unsubscribe();
  }

  startAutoRefresh(): void {
    this.refreshSubscription = interval(3000)
      .pipe(switchMap(() => this.taskService.listTasks(
        this.statusFilter === 'all' ? undefined : this.statusFilter,
        this.typeFilter === 'all' ? undefined : this.typeFilter
      )))
      .subscribe(tasks => {
        // 保留当前页码和展开状态，只更新任务数据
        const currentTaskIds = new Set(this.tasks.map(t => t.id));
        const expandedTaskIds = new Set(
          this.tasks.filter(t => t.expanded).map(t => t.id)
        );
        
        // 更新任务数据，但保留展开状态
        this.tasks = tasks.map(task => {
          const existingTask = this.tasks.find(t => t.id === task.id);
          return {
            ...task,
            expanded: existingTask?.expanded || false
          };
        });
        // 不重置页码，保持当前页
      });
  }

  loadTasks(): void {
    this.isLoading = true;
    this.taskService.listTasks(
      this.statusFilter === 'all' ? undefined : this.statusFilter,
      this.typeFilter === 'all' ? undefined : this.typeFilter
    ).subscribe({
      next: (tasks) => {
        // 只在首次加载或筛选时重置页码，刷新时保持当前页
        this.tasks = tasks.map(task => {
          const existingTask = this.tasks.find(t => t.id === task.id);
          return {
            ...task,
            expanded: existingTask?.expanded || false
          };
        });
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading tasks:', error);
        this.isLoading = false;
      }
    });
  }

  filterByStatus(status: TaskStatus | 'all'): void {
    this.statusFilter = status;
    this.loadTasks();
    this.refreshSubscription?.unsubscribe();
    this.startAutoRefresh();
  }

  filterByType(type: TaskType | 'all'): void {
    this.typeFilter = type;
    this.loadTasks();
    this.refreshSubscription?.unsubscribe();
    this.startAutoRefresh();
  }

  get filteredTasks(): ImportTask[] {
    return this.tasks.filter(task => {
      const statusMatch = this.statusFilter === 'all' || task.status === this.statusFilter;
      const typeMatch = this.typeFilter === 'all' || task.task_type === this.typeFilter;
      return statusMatch && typeMatch;
    });
  }

  // 分页相关方法
  get totalPages(): number {
    return Math.ceil(this.filteredTasks.length / this.pageSize);
  }

  get paginatedTasks(): ImportTask[] {
    const start = this.currentPage * this.pageSize;
    return this.filteredTasks.slice(start, start + this.pageSize);
  }

  get startIndex(): number {
    return this.currentPage * this.pageSize;
  }

  get endIndex(): number {
    const end = (this.currentPage + 1) * this.pageSize;
    return end > this.filteredTasks.length ? this.filteredTasks.length : end;
  }

  get pageNumbers(): number[] {
    return Array.from({ length: this.totalPages }, (_, i) => i);
  }

  changePage(page: number): void {
    if (page < 0 || page >= this.totalPages) return;
    this.currentPage = page;
    this.expandedTaskId = null; // 切换页面时关闭展开的详情
  }

  toggleExpand(task: ImportTask): void {
    if (this.expandedTaskId === task.id) {
      // 关闭展开
      this.expandedTaskId = null;
    } else {
      // 展开并加载完整日志
      this.expandedTaskId = task.id;
      this.loadTaskFullLogs(task);
      
      // 等待视图更新后滚动到详情容器
      setTimeout(() => {
        const detailElement = document.getElementById(`detail-${task.id}`);
        if (detailElement) {
          detailElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
      }, 100);
    }
  }

  loadTaskFullLogs(task: ImportTask): void {
    // 加载任务的完整日志
    this.taskService.getTask(task.id).subscribe({
      next: (detail) => {
        // 更新该任务的日志为完整日志
        const taskIndex = this.tasks.findIndex(t => t.id === task.id);
        if (taskIndex !== -1) {
          this.tasks[taskIndex] = {
            ...this.tasks[taskIndex],
            task_logs: detail.task_logs,
            log_count: detail.task_logs?.length || 0
          };
        }
        
        // 日志加载完成后，再次滚动确保底部可见
        setTimeout(() => {
          const detailElement = document.getElementById(`detail-${task.id}`);
          if (detailElement) {
            detailElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          }
        }, 100);
      },
      error: (error) => {
        console.error('Error loading task logs:', error);
      }
    });
  }

  isExpanded(task: ImportTask): boolean {
    return this.expandedTaskId === task.id;
  }

  viewTaskDetail(task: ImportTask): void {
    this.taskService.getTask(task.id).subscribe({
      next: (detail) => {
        let message = `任务详情:\n\n`;
        message += `名称：${detail.task_name}\n`;
        message += `类型：${this.getTaskTypeName(detail.task_type)}\n`;
        message += `状态：${this.getStatusName(detail.status)}\n`;
        message += `进度：${detail.processed_items}/${detail.total_items} (${detail.progress_percentage.toFixed(1)}%)\n`;
        if (detail.input_url) message += `\n源 URL: ${detail.input_url}\n`;
        if (detail.input_path) message += `\n源路径：${detail.input_path}\n`;
        if (detail.error_message) message += `\n错误信息:\n${detail.error_message}`;
        alert(message);
      },
      error: (error) => {
        console.error('Error loading task detail:', error);
        alert('加载任务详情失败');
      }
    });
  }

  cancelTask(task: ImportTask): void {
    if (confirm(`确定要取消任务 "${task.task_name}" 吗？`)) {
      this.taskService.cancelTask(task.id).subscribe({
        next: () => {
          this.loadTasks();
        },
        error: (error) => {
          console.error('Error cancelling task:', error);
          alert('取消任务失败');
        }
      });
    }
  }

  deleteTask(task: ImportTask): void {
    if (confirm(`确定要删除任务 "${task.task_name}" 吗？`)) {
      this.taskService.deleteTask(task.id).subscribe({
        next: () => {
          this.loadTasks();
        },
        error: (error) => {
          console.error('Error deleting task:', error);
          alert('删除任务失败');
        }
      });
    }
  }

  getStatusName(status: TaskStatus): string {
    switch (status) {
      case 'pending': return '等待中';
      case 'running': return '运行中';
      case 'completed': return '已完成';
      case 'failed': return '失败';
      case 'cancelled': return '已取消';
      default: return '未知';
    }
  }

  getTaskTypeName(type: TaskType): string {
    switch (type) {
      case 'web': return '网页';
      case 'local_file': return '本地文件';
      case 'video': return '视频';
      default: return '其他';
    }
  }

  getLogLevelName(level: string): string {
    switch (level) {
      case 'info': return '信息';
      case 'success': return '成功';
      case 'warning': return '警告';
      case 'error': return '错误';
      default: return level;
    }
  }

  openLogsDialog(task: ImportTask): void {
    // 加载任务的完整日志
    this.taskService.getTask(task.id).subscribe({
      next: (detail) => {
        this.dialog.open(TaskLogsDialogComponent, {
          width: '800px',
          maxWidth: '90vw',
          maxHeight: '80vh',
          data: {
            taskName: task.task_name,
            logs: detail.task_logs || []
          }
        });
      },
      error: (error) => {
        console.error('Error loading task logs:', error);
        alert('加载日志失败');
      }
    });
  }
}

// 日志弹窗组件
@Component({
  selector: 'app-task-logs-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule],
  template: `
    <div class="dialog-header">
      <h2 class="dialog-title">
        <i class="fa-solid fa-list-ul"></i>
        执行日志 - {{ data.taskName }}
      </h2>
      <button class="btn-icon" mat-icon-button (click)="dialogRef.close()">
        <i class="fa-solid fa-times"></i>
      </button>
    </div>
    
    <div class="dialog-content">
      <div class="logs-container">
        <div class="log-entry" *ngFor="let log of data.logs" [class]="'log-' + log.level">
          <div class="log-header">
            <span class="log-time">{{ log.timestamp | date:'yyyy-MM-dd HH:mm:ss' }}</span>
            <span class="log-level-badge" [class]="'badge-' + log.level">
              <i class="fa-solid" 
                 [class.fa-circle-info]="log.level === 'info'"
                 [class.fa-circle-check]="log.level === 'success'"
                 [class.fa-circle-exclamation]="log.level === 'warning'"
                 [class.fa-circle-xmark]="log.level === 'error'">
              </i>
              {{ getLogLevelName(log.level) }}
            </span>
          </div>
          <div class="log-message">{{ log.message }}</div>
          <div class="log-detail" *ngIf="log.detail">{{ log.detail | json }}</div>
        </div>
        
        <div *ngIf="!data.logs || data.logs.length === 0" class="empty-state">
          <i class="fa-regular fa-folder-open"></i>
          <p>暂无执行日志</p>
        </div>
      </div>
    </div>
    
    <div class="dialog-actions">
      <button mat-button (click)="dialogRef.close()">关闭</button>
    </div>
  `,
  styles: [`
    .dialog-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 24px;
      border-bottom: 1px solid #f0f0f0;
      background: #fff;
    }

    .dialog-title {
      font-size: 18px;
      font-weight: 600;
      color: #1f1f1f;
      margin: 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .dialog-content {
      padding: 24px;
      max-height: calc(80vh - 140px);
      overflow-y: auto;
    }

    .logs-container {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .log-entry {
      padding: 12px;
      border-radius: 4px;
      border-left: 3px solid;
      background: #fafafa;
    }

    .log-info {
      border-left-color: #1677ff;
      background: #e6f4ff;
    }

    .log-success {
      border-left-color: #52c41a;
      background: #f6ffed;
    }

    .log-warning {
      border-left-color: #faad14;
      background: #fffbe6;
    }

    .log-error {
      border-left-color: #ff4d4f;
      background: #fff2f0;
    }

    .log-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 8px;
    }

    .log-time {
      font-size: 12px;
      color: #8c8c8c;
    }

    .log-level-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 500;
    }

    .badge-info {
      background: #1677ff;
      color: #fff;
    }

    .badge-success {
      background: #52c41a;
      color: #fff;
    }

    .badge-warning {
      background: #faad14;
      color: #fff;
    }

    .badge-error {
      background: #ff4d4f;
      color: #fff;
    }

    .log-message {
      font-size: 14px;
      color: #262626;
      line-height: 1.6;
      word-break: break-word;
    }

    .log-detail {
      margin-top: 8px;
      padding: 8px;
      background: rgba(0, 0, 0, 0.05);
      border-radius: 4px;
      font-family: monospace;
      font-size: 12px;
      color: #595959;
      overflow-x: auto;
      white-space: pre-wrap;
    }

    .empty-state {
      text-align: center;
      padding: 40px 20px;
      color: #8c8c8c;
    }

    .empty-state i {
      font-size: 48px;
      margin-bottom: 16px;
    }

    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      padding: 16px 24px;
      border-top: 1px solid #f0f0f0;
      background: #fff;
    }

    .btn-icon {
      background: transparent;
      border: none;
      cursor: pointer;
      padding: 8px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }

    .btn-icon:hover {
      background: #f5f5f5;
    }

    .btn-icon i {
      font-size: 16px;
      color: #8c8c8c;
    }
  `]
})
export class TaskLogsDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<TaskLogsDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: { taskName: string; logs: any[] }
  ) {}

  getLogLevelName(level: string): string {
    switch (level) {
      case 'info': return '信息';
      case 'success': return '成功';
      case 'warning': return '警告';
      case 'error': return '错误';
      default: return level;
    }
  }
}
