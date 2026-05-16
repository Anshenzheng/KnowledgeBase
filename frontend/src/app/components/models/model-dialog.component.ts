import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatDialogModule, MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { MatSliderModule } from '@angular/material/slider';

@Component({
  selector: 'app-model-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatDialogModule,
    MatSliderModule
  ],
  template: `
    <h2 mat-dialog-title>{{ data.model ? '编辑模型' : '添加模型' }}</h2>
    
    <mat-dialog-content class="dialog-content">
      <form>
        <!-- 模型类型选择 -->
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>模型类型</mat-label>
          <mat-select [(ngModel)]="modelType" name="modelType" disabled>
            <mat-option value="chat">Chat 模型</mat-option>
            <mat-option value="embedding">Embedding 模型</mat-option>
          </mat-select>
        </mat-form-field>

        <!-- 预置模型选择 -->
        <mat-form-field appearance="outline" class="full-width" *ngIf="!data.model && modelType === 'chat'">
          <mat-label>选择预置模型</mat-label>
          <mat-select (selectionChange)="onPresetChange($event.value)">
            <mat-option value="">自定义配置</mat-option>
            <mat-option value="openai_gpt4">OpenAI GPT-4</mat-option>
            <mat-option value="openai_gpt4o">OpenAI GPT-4o</mat-option>
            <mat-option value="openai_gpt35">OpenAI GPT-3.5 Turbo</mat-option>
            <mat-option value="gemini_pro">Google Gemini Pro</mat-option>
            <mat-option value="gemini_flash">Google Gemini 1.5 Flash</mat-option>
            <mat-option value="deepseek_chat">DeepSeek Chat</mat-option>
            <mat-option value="deepseek_coder">DeepSeek Coder</mat-option>
          </mat-select>
        </mat-form-field>

        <!-- 预置 Embedding 模型选择 -->
        <mat-form-field appearance="outline" class="full-width" *ngIf="!data.model && modelType === 'embedding'">
          <mat-label>选择预置模型</mat-label>
          <mat-select (selectionChange)="onPresetChange($event.value)">
            <mat-option value="">自定义配置</mat-option>
            <mat-option value="zhipu_embedding">智谱 AI Embedding</mat-option>
            <mat-option value="openai_text_embedding">OpenAI Text Embedding</mat-option>
            <mat-option value="gemini_embedding">Google Gemini Embedding</mat-option>
          </mat-select>
          <mat-hint *ngIf="isPresetSelected">选择"自定义配置"可手动编辑提供商和模型名称</mat-hint>
        </mat-form-field>

        <!-- 两列布局 -->
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>提供商</mat-label>
            <mat-select [(ngModel)]="modelData.provider" name="provider" (selectionChange)="onProviderChange()" [disabled]="isPresetSelected">
              <mat-option value="openai">OpenAI</mat-option>
              <mat-option value="gemini">Google Gemini</mat-option>
              <mat-option value="deepseek">DeepSeek</mat-option>
              <mat-option value="zhipu">智谱 AI</mat-option>
              <mat-option value="custom">自定义</mat-option>
            </mat-select>
          </mat-form-field>

          <mat-form-field appearance="outline" class="half-width">
            <mat-label>模型名称</mat-label>
            <input matInput [(ngModel)]="modelData.model_name" name="model_name" placeholder="gpt-4" [disabled]="isPresetSelected">
          </mat-form-field>
        </div>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>显示名称</mat-label>
          <input matInput [(ngModel)]="modelData.display_name" name="display_name" placeholder="例如：GPT-4">
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>API Key</mat-label>
          <input matInput [(ngModel)]="modelData.api_key" name="api_key" type="password" placeholder="输入您的 API 密钥">
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>API Base URL</mat-label>
          <input matInput [(ngModel)]="modelData.base_url" name="base_url" placeholder="https://api.openai.com/v1">
        </mat-form-field>

        <!-- 高级设置 (仅 Chat 模型需要) -->
        <div class="advanced-section" *ngIf="modelType === 'chat'">
          <div class="section-header" (click)="showAdvanced = !showAdvanced">
            <span>高级设置</span>
            <mat-icon>{{ showAdvanced ? 'expand_more' : 'expand_less' }}</mat-icon>
          </div>
          
          <div class="advanced-content" *ngIf="showAdvanced">
            <div class="form-row">
              <div class="slider-container half-width">
                <span class="slider-label">Temperature: {{ modelData.temperature }}</span>
                <mat-slider min="0" max="2" step="0.1" class="full-width">
                  <input matSliderThumb [(ngModel)]="modelData.temperature" name="temperature">
                </mat-slider>
              </div>

              <mat-form-field appearance="outline" class="half-width">
                <mat-label>Max Tokens</mat-label>
                <input matInput [(ngModel)]="modelData.max_tokens" name="max_tokens" type="number">
              </mat-form-field>
            </div>
          </div>
        </div>

        <!-- 开关按钮 -->
        <div class="toggle-row">
          <mat-slide-toggle [(ngModel)]="modelData.is_active" name="is_active">
            启用此模型
          </mat-slide-toggle>

          <mat-slide-toggle [(ngModel)]="modelData.is_default" name="is_default">
            设为默认模型
          </mat-slide-toggle>
        </div>
      </form>
    </mat-dialog-content>

    <mat-dialog-actions align="end">
      <button mat-button (click)="dialogRef.close()">取消</button>
      <button mat-raised-button color="primary" (click)="save()" [disabled]="!isValid()">
        保存
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .dialog-content {
      min-width: 500px;
      max-width: 600px;
    }
    
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
    
    .half-width {
      width: 100%;
      margin-bottom: 0;
    }
    
    .form-row {
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
      
      .half-width {
        flex: 1;
        min-width: 0;
      }
    }
    
    .slider-container {
      .slider-label {
        display: block;
        margin-bottom: 8px;
        color: #666;
        font-size: 13px;
      }
      
      .full-width {
        width: 100%;
      }
    }
    
    .toggle-row {
      display: flex;
      gap: 16px;
      margin-top: 8px;
      align-items: center;
      
      mat-slide-toggle {
        flex: 1;
      }
    }
    
    .advanced-section {
      margin: 16px 0;
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      overflow: hidden;
      
      .section-header {
        padding: 12px 16px;
        background-color: #f5f5f5;
        display: flex;
        justify-content: space-between;
        align-items: center;
        cursor: pointer;
        font-weight: 500;
        color: #666;
        font-size: 14px;
        
        &:hover {
          background-color: #eeeeee;
        }
        
        mat-icon {
          color: #999;
          font-size: 20px;
          width: 20px;
          height: 20px;
        }
      }
      
      .advanced-content {
        padding: 16px;
        background-color: #fafafa;
        
        .form-row {
          margin-bottom: 0;
        }
      }
    }
  `]
})
export class ModelDialogComponent {
  showAdvanced = false;
  modelType: 'chat' | 'embedding' = 'chat';
  isPresetSelected = false;
  
  modelData: any = {
    provider: 'openai',
    model_name: '',
    display_name: '',
    api_key: '',
    base_url: '',
    temperature: 0.7,
    max_tokens: 2000,
    is_active: true,
    is_default: false,
    model_type: 'chat'
  };

  // 预置模型配置
  private presets: any = {
    openai_gpt4: {
      provider: 'openai',
      model_name: 'gpt-4',
      display_name: 'GPT-4',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.7,
      max_tokens: 4096
    },
    openai_gpt4o: {
      provider: 'openai',
      model_name: 'gpt-4o',
      display_name: 'GPT-4o',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.7,
      max_tokens: 4096
    },
    openai_gpt35: {
      provider: 'openai',
      model_name: 'gpt-3.5-turbo',
      display_name: 'GPT-3.5 Turbo',
      base_url: 'https://api.openai.com/v1',
      temperature: 0.7,
      max_tokens: 4096
    },
    gemini_pro: {
      provider: 'gemini',
      model_name: 'gemini-pro',
      display_name: 'Gemini Pro',
      base_url: 'https://generativelanguage.googleapis.com/v1beta',
      temperature: 0.7,
      max_tokens: 2048
    },
    gemini_flash: {
      provider: 'gemini',
      model_name: 'gemini-1.5-flash',
      display_name: 'Gemini 1.5 Flash',
      base_url: 'https://generativelanguage.googleapis.com/v1beta',
      temperature: 0.7,
      max_tokens: 8192
    },
    deepseek_chat: {
      provider: 'deepseek',
      model_name: 'deepseek-chat',
      display_name: 'DeepSeek Chat',
      base_url: 'https://api.deepseek.com/v1',
      temperature: 0.7,
      max_tokens: 4096
    },
    deepseek_coder: {
      provider: 'deepseek',
      model_name: 'deepseek-coder',
      display_name: 'DeepSeek Coder',
      base_url: 'https://api.deepseek.com/v1',
      temperature: 0.7,
      max_tokens: 4096
    },
    // Embedding 模型预设
    zhipu_embedding: {
      provider: 'zhipu',
      model_name: 'embedding-2',
      display_name: '智谱 AI Embedding',
      base_url: 'https://open.bigmodel.cn/api/paas/v4',
      model_type: 'embedding'
    },
    openai_text_embedding: {
      provider: 'openai',
      model_name: 'text-embedding-3-small',
      display_name: 'OpenAI Text Embedding',
      base_url: 'https://api.openai.com/v1',
      model_type: 'embedding'
    },
    gemini_embedding: {
      provider: 'gemini',
      model_name: 'models/embedding-001',
      display_name: 'Google Gemini Embedding',
      base_url: 'https://generativelanguage.googleapis.com/v1beta',
      model_type: 'embedding'
    }
  };

  constructor(
    public dialogRef: MatDialogRef<ModelDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: any
  ) {
    // 设置模型类型
    if (data.modelType) {
      this.modelType = data.modelType;
      this.modelData.model_type = data.modelType;
    }
    
    if (data.model) {
      this.modelData = { ...data.model };
      this.modelType = data.model.model_type || 'chat';
    } else if (data.preset) {
      this.modelData = {
        ...this.modelData,
        ...data.preset
      };
    }
  }

  onPresetChange(presetKey: string): void {
    this.isPresetSelected = !!presetKey;
    if (presetKey && this.presets[presetKey]) {
      this.modelData = {
        ...this.modelData,
        ...this.presets[presetKey]
      };
    }
  }

  onProviderChange(): void {
    // 根据提供商自动设置默认的 base_url
    const defaultUrls: any = {
      openai: 'https://api.openai.com/v1',
      gemini: 'https://generativelanguage.googleapis.com/v1beta',
      deepseek: 'https://api.deepseek.com/v1',
      custom: ''
    };
    
    if (defaultUrls[this.modelData.provider]) {
      this.modelData.base_url = defaultUrls[this.modelData.provider];
    }
  }

  isValid(): boolean {
    return !!(this.modelData.model_name && this.modelData.display_name);
  }

  save(): void {
    if (this.isValid()) {
      this.dialogRef.close(this.modelData);
    }
  }
}
