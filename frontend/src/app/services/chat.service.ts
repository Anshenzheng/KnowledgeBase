import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Message {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  citations?: any[];
  created_at?: string;
}

export interface ChatSession {
  session_id: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ChatRequest {
  content: string;
  session_id?: string;
  model_id?: string;
  use_knowledge?: boolean;
  top_k?: number;
}

export interface ChatResponse {
  message_id: string;
  session_id: string;
  content: string;
  citations: any[];
  model_name: string;
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private readonly apiUrl = '/api/chat';

  constructor(private http: HttpClient) { }

  createSession(title?: string, modelId?: string): Observable<ChatSession> {
    return this.http.post<ChatSession>(`${this.apiUrl}/sessions`, { title, model_id: modelId });
  }

  listSessions(): Observable<ChatSession[]> {
    return this.http.get<ChatSession[]>(`${this.apiUrl}/sessions`);
  }

  sendMessage(request: ChatRequest): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${this.apiUrl}/messages`, request);
  }

  getSessionMessages(sessionId: string): Observable<Message[]> {
    return this.http.get<Message[]>(`${this.apiUrl}/sessions/${sessionId}/messages`);
  }

  deleteSession(sessionId: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/sessions/${sessionId}`);
  }

  deleteAllSessions(): Observable<any> {
    return this.http.delete(`${this.apiUrl}/sessions`);
  }
}
