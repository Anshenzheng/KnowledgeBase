import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Model {
  id: string;
  provider: string;
  model_name: string;
  display_name: string;
  base_url?: string;
  temperature: number;
  max_tokens: number;
  is_active: boolean;
  is_default: boolean;
  model_type?: 'chat' | 'embedding';
}

export interface ModelCreate {
  provider: string;
  model_name: string;
  display_name: string;
  api_key?: string;
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
  is_active?: boolean;
  is_default?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ModelService {
  private readonly apiUrl = '/api/models';

  constructor(private http: HttpClient) { }

  listModels(): Observable<Model[]> {
    return this.http.get<Model[]>(this.apiUrl);
  }

  getModel(id: string): Observable<Model> {
    return this.http.get<Model>(`${this.apiUrl}/${id}`);
  }

  createModel(model: ModelCreate): Observable<Model> {
    return this.http.post<Model>(this.apiUrl, model);
  }

  updateModel(id: string, model: Partial<ModelCreate>): Observable<Model> {
    return this.http.put<Model>(`${this.apiUrl}/${id}`, model);
  }

  deleteModel(id: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/${id}`);
  }

  getPresets(): Observable<any[]> {
    return this.http.get<any[]>(`${this.apiUrl}/presets`);
  }

  getDefaultEmbeddingModel(): Observable<Model> {
    return this.http.get<Model>(`${this.apiUrl}/embedding/default`);
  }
}
