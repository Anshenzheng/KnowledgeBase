import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ImportTask {
  id: string;
  task_name: string;
  task_type: 'web' | 'local_file' | 'video';
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress_percentage: number;
  total_items: number;
  processed_items: number;
  failed_items: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  result_summary?: any;
  input_url?: string;
  input_path?: string;
  max_depth?: number;
  strategy?: 'skip' | 'overwrite' | 'add_new';
  log_count?: number;
  recent_logs?: TaskLog[];
  task_logs?: TaskLog[]; // 保留向后兼容
  expanded?: boolean; // UI 状态字段
}

export interface TaskLog {
  timestamp: string;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
  detail?: any;
}

export interface WebImportRequest {
  url: string;
  max_depth?: number;
  strategy?: 'skip' | 'overwrite' | 'add_new';
  task_name?: string;
}

export interface LocalImportRequest {
  directory_path: string;
  strategy?: 'skip' | 'overwrite' | 'add_new';
  task_name?: string;
}

export interface VideoImportRequest {
  url?: string;
  file_path?: string;
  strategy?: 'skip' | 'overwrite' | 'add_new';
  task_name?: string;
}

@Injectable({
  providedIn: 'root'
})
export class KnowledgeService {
  private readonly apiUrl = '/api/knowledge';

  constructor(private http: HttpClient) { }

  importWeb(request: WebImportRequest): Observable<{ task_id: string; message: string }> {
    return this.http.post<{ task_id: string; message: string }>(`${this.apiUrl}/import/web`, request);
  }

  importLocal(request: LocalImportRequest): Observable<{ task_id: string; message: string }> {
    return this.http.post<{ task_id: string; message: string }>(`${this.apiUrl}/import/local`, request);
  }

  importVideo(request: VideoImportRequest): Observable<{ task_id: string; message: string }> {
    return this.http.post<{ task_id: string; message: string }>(`${this.apiUrl}/import/video`, request);
  }

  uploadFile(file: File, taskName?: string, strategy?: 'skip' | 'overwrite' | 'add_new'): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);
    if (taskName) {
      formData.append('task_name', taskName);
    }
    if (strategy) {
      formData.append('strategy', strategy);
    }
    return this.http.post(`${this.apiUrl}/upload/file`, formData);
  }

  uploadFiles(files: File[], taskName?: string, strategy?: 'skip' | 'overwrite' | 'add_new'): Observable<any> {
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    if (taskName) {
      formData.append('task_name', taskName);
    }
    if (strategy) {
      formData.append('strategy', strategy);
    }
    return this.http.post(`${this.apiUrl}/upload/files`, formData);
  }

  uploadVideo(formData: FormData): Observable<{ task_id: string; message: string }> {
    return this.http.post<{ task_id: string; message: string }>(`${this.apiUrl}/upload/video`, formData);
  }
}
