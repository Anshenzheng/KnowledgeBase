import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { ModelService, Model, ModelCreate } from '../../services/model.service';
import { ModelDialogComponent } from './model-dialog.component';

@Component({
  selector: 'app-models',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatSnackBarModule,
    MatDialogModule
  ],
  templateUrl: './models.component.html',
  styleUrls: ['./models.component.scss']
})
export class ModelsComponent implements OnInit {
  models: Model[] = [];
  embeddingModels: Model[] = [];
  isLoading = false;
  isLoadingEmbedding = false;
  presets: any[] = [];
  activeTab: 'chat' | 'embedding' = 'chat';

  constructor(
    private modelService: ModelService,
    private dialog: MatDialog,
    private snackBar: MatSnackBar
  ) { }

  ngOnInit(): void {
    this.loadModels();
    this.loadEmbeddingModels();
    this.loadPresets();
  }

  loadModels(): void {
    this.isLoading = true;
    this.modelService.listModels().subscribe({
      next: (models) => {
        this.models = models.filter(m => m.model_type !== 'embedding');
        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error loading models:', error);
        this.isLoading = false;
        this.snackBar.open('加载模型列表失败', '关闭', { duration: 3000 });
      }
    });
  }

  loadEmbeddingModels(): void {
    this.isLoadingEmbedding = true;
    this.modelService.listModels().subscribe({
      next: (models) => {
        this.embeddingModels = models.filter(m => m.model_type === 'embedding');
        this.isLoadingEmbedding = false;
      },
      error: (error) => {
        console.error('Error loading embedding models:', error);
        this.isLoadingEmbedding = false;
        this.snackBar.open('加载 Embedding 模型列表失败', '关闭', { duration: 3000 });
      }
    });
  }

  loadPresets(): void {
    this.modelService.getPresets().subscribe(presets => {
      this.presets = presets;
    });
  }

  openAddDialog(preset?: any): void {
    const dialogRef = this.dialog.open(ModelDialogComponent, {
      width: '600px',
      data: { preset, modelType: this.activeTab === 'embedding' ? 'embedding' : 'chat' }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.modelService.createModel(result).subscribe({
          next: () => {
            if (this.activeTab === 'embedding') {
              this.loadEmbeddingModels();
            } else {
              this.loadModels();
            }
            this.snackBar.open('模型添加成功', '关闭', { duration: 3000 });
          },
          error: (error) => {
            console.error('Error creating model:', error);
            this.snackBar.open('添加模型失败', '关闭', { duration: 3000 });
          }
        });
      }
    });
  }

  openEditDialog(model: Model): void {
    const dialogRef = this.dialog.open(ModelDialogComponent, {
      width: '600px',
      data: { model, modelType: this.activeTab === 'embedding' ? 'embedding' : 'chat' }
    });

    dialogRef.afterClosed().subscribe(result => {
      if (result) {
        this.modelService.updateModel(model.id, result).subscribe({
          next: () => {
            if (this.activeTab === 'embedding') {
              this.loadEmbeddingModels();
            } else {
              this.loadModels();
            }
            this.snackBar.open('模型更新成功', '关闭', { duration: 3000 });
          },
          error: (error) => {
            console.error('Error updating model:', error);
            this.snackBar.open('更新模型失败', '关闭', { duration: 3000 });
          }
        });
      }
    });
  }

  deleteModel(model: Model): void {
    if (confirm(`确定要删除模型 "${model.display_name}" 吗？`)) {
      this.modelService.deleteModel(model.id).subscribe({
        next: () => {
          this.loadModels();
          this.snackBar.open('模型已删除', '关闭', { duration: 3000 });
        },
        error: (error) => {
          console.error('Error deleting model:', error);
          this.snackBar.open('删除模型失败', '关闭', { duration: 3000 });
        }
      });
    }
  }

  setAsDefault(model: Model): void {
    this.modelService.updateModel(model.id, { is_default: true }).subscribe({
      next: () => {
        this.loadModels();
        this.snackBar.open('默认模型已设置', '关闭', { duration: 3000 });
      },
      error: (error) => {
        console.error('Error setting default model:', error);
        this.snackBar.open('设置默认模型失败', '关闭', { duration: 3000 });
      }
    });
  }

  trackByModelId(index: number, model: Model): string {
    return model.id;
  }
}
