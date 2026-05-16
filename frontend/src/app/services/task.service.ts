import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ImportTask } from './knowledge.service';

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TaskType = 'web' | 'local_file' | 'video';

@Injectable({
  providedIn: 'root'
})
export class TaskService {
  private readonly apiUrl = '/api/tasks';

  constructor(private http: HttpClient) { }

  listTasks(status?: TaskStatus, taskType?: TaskType, limit: number = 50): Observable<ImportTask[]> {
    let params: any = { limit: limit.toString() };
    if (status) params.status = status;
    if (taskType) params.task_type = taskType;
    return this.http.get<ImportTask[]>(this.apiUrl, { params });
  }

  getTask(id: string): Observable<ImportTask> {
    return this.http.get<ImportTask>(`${this.apiUrl}/${id}`);
  }

  deleteTask(id: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/${id}`);
  }

  cancelTask(id: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/${id}/cancel`, {});
  }
}
