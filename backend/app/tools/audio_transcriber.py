"""
Audio Extraction and Speech-to-Text Tool using Whisper - Asynchronous Production Optimized
"""
import os
import sys
import torch
import shutil
import whisper
import anyio
import subprocess
from pathlib import Path
from loguru import logger
from typing import Optional, Dict, List, Any


class AudioTranscriber:
    """Extract audio from video and transcribe to text asynchronously without blocking the event loop"""
    
    # 类级别的模型缓存，避免重复加载相同模型
    _model_cache = {}
    
    def __init__(self, model_size: str = "base", device: Optional[str] = None):
        """
        Initialize Whisper model inside synchronous safe wrapper
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: 'cuda', 'cpu', or None for automatic detection
        """
        # 建立安全的配置垫片：优先读取系统 settings，读取失败则降级使用标准临时目录
        upload_dir = "/tmp/app_uploads"
        try:
            from app.config import settings
            if hasattr(settings, "UPLOAD_DIR"):
                upload_dir = settings.UPLOAD_DIR
        except ImportError:
            logger.warning("app.config.settings not found. Using default temporary upload path.")

        self.audio_dir = os.path.join(upload_dir, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)
        self.model_size = model_size
        
        # 1. 硬件自适应选择：最大化榨干服务器 GPU 算力性能
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        logger.info(f"Initializing Whisper Context. Target Model: {model_size} | Execution Device: {self.device}")
        
        # 2. 使用模型缓存避免重复加载（每个模型只加载一次）
        cache_key = f"{model_size}_{self.device}"
        if cache_key not in AudioTranscriber._model_cache:
            logger.info(f"Loading Whisper model '{model_size}' for the first time (caching enabled)")
            AudioTranscriber._model_cache[cache_key] = whisper.load_model(model_size, device=self.device)
            logger.success(f"Whisper model '{model_size}' loaded and cached successfully on device: {self.device}")
        else:
            logger.info(f"Using cached Whisper model '{model_size}' on device: {self.device}")
        
        self.model = AudioTranscriber._model_cache[cache_key]

    def _extract_audio_sync(self, video_path: str, audio_output_path: str) -> str:
        """
        同步 FFmpeg 执行内核（由独立工作线程池托管）
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Source video file not found at: {video_path}")
            
        # 优化核心：直接提取为 Whisper 内部最喜欢的 16kHz、单声道、无损 WAV 格式，杜绝二次重采样带来的音质磨损
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',                  # 禁用视频流输出，极大加快提取速度
            '-acodec', 'pcm_s16le', # 16bit PCM 线性编码
            '-ar', '16000',         # 16kHz 采样率 (Whisper 的标准输入基准)
            '-ac', '1',             # 单声道 (Mono)
            '-y',                   # 强制覆盖已存在的音频目标文件
            audio_output_path
        ]
        
        try:
            logger.debug(f"Executing FFmpeg subprocess pipeline for: {Path(video_path).name}")
            # 捕获 stderr 用于精准排查音视频封装、损坏错误
            result = subprocess.run(cmd, check=True, capture_output=True, text=False)
            return audio_output_path
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "Unknown Subprocess Error"
            logger.error(f"FFmpeg pipeline crashed: {error_msg}")
            raise RuntimeError(f"Audio extraction crashed at system level: {error_msg}")
        except FileNotFoundError:
            logger.critical("System executable binary 'ffmpeg' is missing from the environment PATH.")
            raise RuntimeError(
                "ffmpeg binary not found. Please install ffmpeg:\n"
                "  Windows: winget install ffmpeg  OR  choco install ffmpeg\n"
                "  macOS: brew install ffmpeg\n"
                "  Linux: sudo apt-get install ffmpeg  OR  sudo yum install ffmpeg"
            )

    async def extract_audio(self, video_path: str, audio_output_path: Optional[str] = None) -> str:
        """
        异步非阻塞音轨提取接口
        """
        if audio_output_path is None:
            # 统一变更为官方契约推荐的无损 .wav 格式，附带模型尺寸后缀防止并发覆盖
            base_name = Path(video_path).stem
            audio_output_path = os.path.join(self.audio_dir, f"{base_name}_{self.model_size}.wav")
            
        # 借助 AnyIO 线程桥接器，把同步阻塞的 FFmpeg 进程移出 FastAPI 主事件循环
        return await anyio.to_thread.run_sync(self._extract_audio_sync, video_path, audio_output_path)

    def _transcribe_sync(self, audio_path: str, language: Optional[str], verbose: bool, cancel_check_callback=None) -> Dict[str, Any]:
        """
        同步 Whisper 推理计算内核（由独立工作线程池托管）
        
        Args:
            cancel_check_callback: 可选的取消检查回调函数，用于中断长时间运行的转录任务
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Target audio file to transcribe not found: {audio_path}")
            
        options = {
            "task": "transcribe",
            "verbose": verbose,
            "fp16": True if self.device == "cuda" else False
        }
        
        if language:
            options["language"] = language

        logger.info(f"Whisper matrix inference triggered for asset: {Path(audio_path).name}")
        
        # 优化 2：长音频分段转写，降低内存占用
        try:
            # 获取音频时长
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                capture_output=True, text=True
            )
            duration = float(result.stdout.strip())
            
            # 如果音频超过 30 分钟，使用分段转写
            if duration > 1800:  # 30 分钟
                logger.info(f"Long audio detected ({duration:.1f}s), using segmented transcription")
                return self._transcribe_segmented(audio_path, options, cancel_check_callback)
            
            # 短音频直接转写
            result = self.model.transcribe(audio_path, **options)
            
        except Exception as e:
            logger.warning(f"Audio duration detection failed: {e}, using standard transcription")
            result = self.model.transcribe(audio_path, **options)
        
        # 使用带取消检查的模型转写
        segments = []
        for segment in result.get("segments", []):
            # 在每处理完一个 segment 后检查取消
            if cancel_check_callback and cancel_check_callback():
                logger.info("Transcription cancelled by user, stopping early")
                break
                
            segments.append({
                "start": round(segment["start"], 2),
                "end": round(segment["end"], 2),
                "text": segment["text"].strip()
            })
            
        # 修复时长失真漏洞：优先通过最后一片的结束标记获取真实的视频/音频总时常
        total_duration = 0.0
        if segments:
            total_duration = segments[-1]["end"]
            
        return {
            "success": True,
            "text": result.get("text", "").strip(),
            "language": result.get("language", "unknown"),
            "segments": segments,
            "duration": round(total_duration, 2)
        }
    
    def _transcribe_segmented(self, audio_path: str, options: dict, cancel_check_callback=None) -> Dict[str, Any]:
        """
        分段转写长音频：每 30 分钟一段，避免内存溢出
        
        Args:
            audio_path: 音频文件路径
            options: Whisper 转写选项
            cancel_check_callback: 取消检查回调
        """
        import subprocess
        import tempfile
        
        # 获取音频时长
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
            capture_output=True, text=True
        )
        total_duration = float(result.stdout.strip())
        
        # 分段参数
        segment_duration = 1800  # 30 分钟一段
        segments = []
        all_text = []
        language = None
        
        logger.info(f"Splitting audio into {int(total_duration / segment_duration) + 1} segments")
        
        try:
            for start_time in range(0, int(total_duration), segment_duration):
                # 检查取消
                if cancel_check_callback and cancel_check_callback():
                    logger.info("Segmented transcription cancelled by user")
                    break
                
                duration = min(segment_duration, total_duration - start_time)
                logger.info(f"Processing segment {start_time/60:.1f}-{(start_time+duration)/60:.1f} min")
                
                # 使用 FFmpeg 切割音频段
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                    temp_path = tmp_file.name
                
                try:
                    cmd = [
                        'ffmpeg', '-i', audio_path, '-ss', str(start_time),
                        '-t', str(duration), '-acodec', 'pcm_s16le',
                        '-ar', '16000', '-ac', '1', '-y', temp_path
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)
                    
                    # 转写当前段
                    segment_result = self.model.transcribe(temp_path, **options)
                    
                    # 合并结果
                    if language is None:
                        language = segment_result.get("language")
                    
                    for segment in segment_result.get("segments", []):
                        # 调整时间戳
                        segments.append({
                            "start": round(start_time + segment["start"], 2),
                            "end": round(start_time + segment["end"], 2),
                            "text": segment["text"].strip()
                        })
                    
                    all_text.append(segment_result.get("text", ""))
                    
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            
            return {
                "success": True,
                "text": "".join(all_text).strip(),
                "language": language or "unknown",
                "segments": segments,
                "duration": round(total_duration, 2),
                "segmented": True
            }
            
        except Exception as e:
            logger.error(f"Segmented transcription failed: {e}")
            # 降级到标准转写
            return self._transcribe_sync(audio_path, options.get("language"), options.get("verbose"), cancel_check_callback)

    async def transcribe(self, audio_path: str, language: Optional[str] = None, verbose: bool = False, cancel_check_callback=None) -> Dict[str, Any]:
        """
        异步非阻塞语音转文字模型推理
        
        Args:
            cancel_check_callback: 可选的取消检查回调函数，用于中断长时间运行的转录任务
        """
        try:
            return await anyio.to_thread.run_sync(self._transcribe_sync, audio_path, language, verbose, cancel_check_callback)
        except Exception as e:
            logger.error(f"Whisper engine inference step collapsed: {e}")
            return {
                "success": False,
                "error": f"Transcription engine collapse: {str(e)}"
            }

    async def process_video(self, video_path: str, language: Optional[str] = None, keep_audio: bool = False, cancel_check_callback=None) -> Dict[str, Any]:
        """
        音视频处理全自动流水线：
        抽取无损 16kHz 单声道波形文件 -> 移交 STT 识别 -> 触发资源全自动自毁清理。
        
        Args:
            video_path: 目标视频文件的绝对或规范化坐标路径
            language: 目标语言的 ISO 编码简写（例如 'zh', 'en'）。设置为 None 则自动触发语种探测。
            keep_audio: 如果设置为 False，转录完毕后中间态产生的无损 .wav 格式音频流会在磁盘上被物理抹除，守护磁盘健康。
            cancel_check_callback: 可选的取消检查回调函数，用于中断长时间运行的转录任务
        """
        audio_path = None
        try:
            # 1. 流水线一阶段：异步非阻塞抽取音频
            audio_path = await self.extract_audio(video_path)
            
            # 2. 流水线二阶段：异步非阻塞大模型矩阵识别
            transcription = await self.transcribe(audio_path, language=language, cancel_check_callback=cancel_check_callback)
            
            if transcription["success"]:
                transcription["video_path"] = video_path
                # 如果用户要求保留资产，则回填磁盘真实路径，否则置空防御隐私泄露
                transcription["audio_path"] = audio_path if keep_audio else None
                
            return transcription
            
        except Exception as pipeline_err:
            logger.critical(f"Media analysis pipeline catastrophic system failure: {pipeline_err}")
            return {
                "success": False,
                "error": f"Media pipeline execution aborted: {str(pipeline_err)}"
            }
        finally:
            # 3. 联动原子级自毁防御机制：只要设定了不保留，无论中间哪个环节（包括大模型崩溃）抛出异常，彻底粉碎残留垃圾音频
            if not keep_audio and audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.debug(f"Transient runtime asset completely cleaned and scrubbed: {Path(audio_path).name}")
                except Exception as clean_err:
                    logger.warning(f"Garbage collection registry failed to sweep temporary file {audio_path}: {clean_err}")