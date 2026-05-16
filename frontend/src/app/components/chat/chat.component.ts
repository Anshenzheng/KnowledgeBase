import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ChatService, Message, ChatSession } from '../../services/chat.service';
import { ModelService, Model } from '../../services/model.service';
import { MarkdownPipe } from '../../pipes/markdown.pipe';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatCheckboxModule,
    MatTooltipModule,
    MatSnackBarModule,
    MarkdownPipe
  ],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.scss']
})
export class ChatComponent implements OnInit, OnDestroy {
  messages: Message[] = [];
  newMessage = '';
  isLoading = false;
  sessions: ChatSession[] = [];
  currentSession: ChatSession | null = null;
  models: Model[] = [];
  selectedModelId: string | null = null;
  useKnowledge = true;
  topK = 5;

  @ViewChild('messagesContainer') messagesContainer!: ElementRef;
  @ViewChild('messageInput') messageInput!: ElementRef;

  private subscriptions = new Subscription();

  constructor(
    private chatService: ChatService,
    private modelService: ModelService,
    private snackBar: MatSnackBar
  ) { }

  ngOnInit(): void {
    this.loadModels();
    this.loadSessions();
    this.createNewSession();
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  loadModels(): void {
    this.subscriptions.add(
      this.modelService.listModels().subscribe(models => {
        this.models = models;
        const defaultModel = models.find(m => m.is_default);
        if (defaultModel) {
          this.selectedModelId = defaultModel.id;
        } else if (models.length > 0) {
          this.selectedModelId = models[0].id;
        }
      })
    );
  }

  loadSessions(): void {
    this.subscriptions.add(
      this.chatService.listSessions().subscribe(sessions => {
        this.sessions = sessions;
      })
    );
  }

  createNewSession(): void {
    this.currentSession = null;
    this.messages = [];
  }

  selectSession(session: ChatSession): void {
    this.currentSession = session;
    this.subscriptions.add(
      this.chatService.getSessionMessages(session.session_id).subscribe(messages => {
        this.messages = messages;
        this.scrollToBottom();
      })
    );
  }

  sendMessage(): void {
    if (!this.newMessage.trim() || this.isLoading) return;

    const message: Message = {
      role: 'user',
      content: this.newMessage.trim()
    };

    this.messages.push(message);
    const userMessage = this.newMessage;
    this.newMessage = '';
    this.isLoading = true;

    setTimeout(() => this.scrollToBottom(), 100);

    this.subscriptions.add(
      this.chatService.sendMessage({
        content: userMessage,
        session_id: this.currentSession?.session_id,
        model_id: this.selectedModelId || undefined,
        use_knowledge: this.useKnowledge,
        top_k: this.topK
      }).subscribe({
        next: (response) => {
          const assistantMessage: Message = {
            role: 'assistant',
            content: response.content,
            citations: response.citations
          };
          this.messages.push(assistantMessage);
          this.isLoading = false;

          // 设置当前会话，使用后端返回的 session_id
          if (!this.currentSession) {
            this.currentSession = {
              session_id: response.session_id,
              title: userMessage.substring(0, 50) + (userMessage.length > 50 ? '...' : ''),
              updated_at: new Date().toISOString()
            };
            this.sessions.unshift(this.currentSession);
          }

          setTimeout(() => this.scrollToBottom(), 100);
        },
        error: (error) => {
          console.error('Error sending message:', error);
          this.isLoading = false;
          setTimeout(() => this.scrollToBottom(), 100);
        }
      })
    );
  }

  scrollToBottom(): void {
    try {
      this.messagesContainer.nativeElement.scrollTop = this.messagesContainer.nativeElement.scrollHeight;
    } catch (err) { }
  }

  trackByMessageId(index: number, message: Message): string {
    return message.id || index.toString();
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  onUseKnowledgeChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    this.useKnowledge = target.checked;
  }

  deleteSession(session: ChatSession): void {
    if (confirm(`确定要删除对话 "${session.title || '新对话'}" 吗？`)) {
      this.subscriptions.add(
        this.chatService.deleteSession(session.session_id).subscribe({
          next: () => {
            this.sessions = this.sessions.filter(s => s.session_id !== session.session_id);
            if (this.currentSession?.session_id === session.session_id) {
              this.createNewSession();
            }
            this.snackBar.open('对话已删除', '关闭', { duration: 3000 });
          },
          error: (error) => {
            console.error('Error deleting session:', error);
            this.snackBar.open('删除对话失败', '关闭', { duration: 3000 });
          }
        })
      );
    }
  }

  deleteAllSessions(): void {
    if (confirm('确定要清空所有对话历史吗？此操作不可恢复！')) {
      this.subscriptions.add(
        this.chatService.deleteAllSessions().subscribe({
          next: () => {
            this.sessions = [];
            this.createNewSession();
            this.snackBar.open('所有对话已清空', '关闭', { duration: 3000 });
          },
          error: (error) => {
            console.error('Error deleting all sessions:', error);
            this.snackBar.open('清空对话失败', '关闭', { duration: 3000 });
          }
        })
      );
    }
  }

  copyMessage(content: string): void {
    // 去除 markdown 格式后复制
    const plainText = content.replace(/```[\s\S]*?```/g, '').replace(/`([^`]+)`/g, '$1');
    navigator.clipboard.writeText(plainText).then(() => {
      this.snackBar.open('内容已复制到剪贴板', '关闭', { duration: 2000 });
    }).catch(err => {
      console.error('Failed to copy:', err);
      this.snackBar.open('复制失败', '关闭', { duration: 2000 });
    });
  }
}
