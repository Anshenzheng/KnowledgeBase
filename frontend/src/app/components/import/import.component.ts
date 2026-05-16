import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Router } from '@angular/router';
import { KnowledgeService } from '../../services/knowledge.service';

export type ImportTab = 'web' | 'upload' | 'video';

@Component({
  selector: 'app-import',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule],
  templateUrl: './import.component.html',
  styleUrls: ['./import.component.scss']
})
export class ImportComponent {
  activeTab: ImportTab = 'web';

  // Web Import
  webUrl = '';
  webMaxDepth = 1;
  webStrategy: 'skip' | 'overwrite' | 'add_new' = 'skip';
  webTaskName = '';
  isImportingWeb = false;

  // File Upload
  selectedFiles: File[] = [];
  uploadStrategy: 'skip' | 'overwrite' | 'add_new' = 'skip';
  uploadTaskName = '';
  isUploading = false;

  // Video Import
  videoSourceType: 'url' | 'local' = 'url';
  videoUrl = '';
  selectedVideoFile: File | null = null;
  videoStrategy: 'skip' | 'overwrite' | 'add_new' = 'skip';
  videoTaskName = '';
  isImportingVideo = false;

  constructor(
    private knowledgeService: KnowledgeService,
    private snackBar: MatSnackBar,
    private router: Router
  ) { }

  setActiveTab(tab: ImportTab): void {
    this.activeTab = tab;
  }

  importWeb(): void {
    if (!this.webUrl.trim()) {
      this.snackBar.open('请输入网址', '关闭', { duration: 3000 });
      return;
    }

    this.isImportingWeb = true;

    this.knowledgeService.importWeb({
      url: this.webUrl,
      max_depth: this.webMaxDepth,
      strategy: this.webStrategy,
      task_name: this.webTaskName || undefined
    }).subscribe({
      next: (response) => {
        const snackRef = this.snackBar.open(`导入任务已创建：${response.task_id}`, '查看任务', {
          duration: 5000
        });
        snackRef.onAction().subscribe(() => {
          this.router.navigate(['/tasks']);
        });
        this.resetWebForm();
        this.isImportingWeb = false;
      },
      error: (error) => {
        console.error('Web import error:', error);
        this.snackBar.open('导入失败：' + (error.error?.detail || '未知错误'), '关闭', { duration: 5000 });
        this.isImportingWeb = false;
      }
    });
  }

  importVideo(): void {
    if (!this.isVideoFormValid()) {
      const errorMsg = this.videoSourceType === 'url' 
        ? '请输入视频 URL' 
        : '请选择视频文件';
      this.snackBar.open(errorMsg, '关闭', { duration: 3000 });
      return;
    }

    this.isImportingVideo = true;

    // 本地文件上传
    if (this.videoSourceType === 'local' && this.selectedVideoFile) {
      const formData = new FormData();
      formData.append('video', this.selectedVideoFile);
      if (this.videoTaskName) {
        formData.append('task_name', this.videoTaskName);
      }
      formData.append('strategy', this.videoStrategy);

      this.knowledgeService.uploadVideo(formData).subscribe({
        next: (response) => {
          const snackRef = this.snackBar.open(`导入任务已创建：${response.task_id}`, '查看任务', {
            duration: 5000
          });
          snackRef.onAction().subscribe(() => {
            this.router.navigate(['/tasks']);
          });
          this.resetVideoForm();
          this.isImportingVideo = false;
        },
        error: (error) => {
          console.error('Video upload error:', error);
          this.snackBar.open('导入失败：' + (error.error?.detail || '未知错误'), '关闭', { duration: 5000 });
          this.isImportingVideo = false;
        }
      });
    } else {
      // 网络视频下载
      this.knowledgeService.importVideo({
        url: this.videoUrl || undefined,
        strategy: this.videoStrategy,
        task_name: this.videoTaskName || undefined
      }).subscribe({
        next: (response) => {
          const snackRef = this.snackBar.open(`导入任务已创建：${response.task_id}`, '查看任务', {
            duration: 5000
          });
          snackRef.onAction().subscribe(() => {
            this.router.navigate(['/tasks']);
          });
          this.resetVideoForm();
          this.isImportingVideo = false;
        },
        error: (error) => {
          console.error('Video import error:', error);
          this.snackBar.open('导入失败：' + (error.error?.detail || '未知错误'), '关闭', { duration: 5000 });
          this.isImportingVideo = false;
        }
      });
    }
  }

  resetWebForm(): void {
    this.webUrl = '';
    this.webTaskName = '';
    this.webMaxDepth = 1;
    this.webStrategy = 'skip';
  }

  resetVideoForm(): void {
    this.videoSourceType = 'url';
    this.videoUrl = '';
    this.selectedVideoFile = null;
    this.videoTaskName = '';
    this.videoStrategy = 'skip';
  }

  onVideoSourceTypeChange(): void {
    // 切换来源类型时清空另一种类型的输入
    if (this.videoSourceType === 'url') {
      this.selectedVideoFile = null;
    } else if (this.videoSourceType === 'local') {
      this.videoUrl = '';
    }
  }

  isVideoFormValid(): boolean {
    if (this.videoSourceType === 'url') {
      return this.videoUrl.trim() !== '';
    } else {
      return this.selectedVideoFile !== null;
    }
  }

  triggerFileInput(): void {
    const fileInput = document.getElementById('fileInput') as HTMLInputElement;
    if (fileInput) {
      fileInput.click();
    }
  }

  triggerVideoFileInput(): void {
    const fileInput = document.getElementById('videoFileInput') as HTMLInputElement;
    if (fileInput) {
      fileInput.click();
    }
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (files && files.length > 0) {
      for (let i = 0; i < files.length; i++) {
        this.selectedFiles.push(files[i]);
      }
      input.value = '';
    }
  }

  onVideoFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (files && files.length > 0) {
      this.selectedVideoFile = files[0];
      input.value = '';
    }
  }

  removeVideoFile(): void {
    this.selectedVideoFile = null;
  }

  removeFile(index: number): void {
    this.selectedFiles.splice(index, 1);
  }

  uploadFiles(): void {
    if (this.selectedFiles.length === 0) {
      this.snackBar.open('请选择要上传的文件', '关闭', { duration: 3000 });
      return;
    }

    this.isUploading = true;

    this.knowledgeService.uploadFiles(
      this.selectedFiles,
      this.uploadTaskName || undefined,
      this.uploadStrategy
    ).subscribe({
      next: (response) => {
        const snackRef = this.snackBar.open(
          `成功上传 ${response.uploaded_files} 个文件，任务 ID: ${response.task_id}`,
          '查看任务',
          { duration: 5000 }
        );
        snackRef.onAction().subscribe(() => {
          this.router.navigate(['/tasks']);
        });
        this.selectedFiles = [];
        this.uploadTaskName = '';
        this.isUploading = false;
      },
      error: (error) => {
        console.error('File upload error:', error);
        let errorMsg = '上传失败：未知错误';
        if (error.error?.detail) {
          errorMsg = '上传失败：' + error.error.detail;
        } else if (error.error) {
          errorMsg = '上传失败：' + JSON.stringify(error.error);
        }
        this.snackBar.open(errorMsg, '关闭', { duration: 5000 });
        this.isUploading = false;
      }
    });
  }
}
