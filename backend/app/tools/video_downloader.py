"""
Video Download Tool using yt-dlp - Production Ready
"""
from typing import Optional, Dict, List
import yt_dlp
import os
from loguru import logger
from app.config import settings


class VideoDownloader:
    """Download videos from various platforms with precise file tracking"""
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(settings.UPLOAD_DIR, "videos")
        os.makedirs(self.output_dir, exist_ok=True)
        self._check_dependencies()

    def _check_dependencies(self):
        """预检查 ffmpeg 依赖"""
        if not yt_dlp.utils.get_exe_version('ffmpeg'):
            logger.warning("ffmpeg is not installed or not in PATH. Video/Audio merging may fail!")

    def download(self, url: str, output_template: Optional[str] = None, cancel_check_callback=None, prefer_audio_only: bool = True, max_height: int = 720) -> Dict:
        """
        Download video from URL (Extract & Download in one single pass)
        
        Args:
            cancel_check_callback: 可选的取消检查回调函数，用于在下载过程中检查是否被取消
            prefer_audio_only: 优先下载音频（True）或视频（False），默认 True 以节省空间
            max_height: 最大视频高度（720p/1080p），默认 720p
        """
        if output_template is None:
            output_template = os.path.join(self.output_dir, "%(title)s.%(ext)s")
        
        real_filepath: Optional[str] = None

        # 通过钩子精准获取 yt-dlp 最终写入磁盘的绝对路径
        def ydl_hook(d: dict):
            nonlocal real_filepath
            if d.get('status') == 'finished':
                real_filepath = d.get('filename')
            # 在下载过程中检查取消
            elif d.get('status') == 'downloading':
                if cancel_check_callback and cancel_check_callback():
                    logger.info("Video download cancelled by user")
                    raise InterruptedError("Download cancelled by user")

        # 优化 1：优先下载音频或限制视频质量，减少磁盘占用和后续处理时间
        if prefer_audio_only:
            # 只下载最佳音频，体积减少 80%+（适合纯语音转录）
            format_str = 'bestaudio/best'
            merge_output_format = 'm4a'
        else:
            # 下载视频但限制最大高度（720p 足够）
            format_str = f'bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]/best'
            merge_output_format = 'mp4'

        ydl_opts = {
            # 优化下载策略：音频优先或限制高度
            'format': format_str,
            'outtmpl': output_template,
            # 合并输出格式
            'merge_output_format': merge_output_format,
            'quiet': True,
            'no_warnings': False,
            'extract_flat': False,
            'progress_hooks': [ydl_hook],
            # 禁用需要 ffmpeg 的后处理（我们自己在 extract_audio 中处理）
            'postprocessors': [],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not real_filepath or not os.path.exists(real_filepath):
                    real_filepath = ydl.prepare_filename(info)
                    base, _ = os.path.splitext(real_filepath)
                    if os.path.exists(f"{base}.m4a"):
                        real_filepath = f"{base}.m4a"
                    elif os.path.exists(f"{base}.mp4"):
                        real_filepath = f"{base}.mp4"

                return {
                    "success": True,
                    "title": info.get('title', 'Unknown'),
                    "duration": info.get('duration', 0),
                    "uploader": info.get('uploader', 'Unknown'),
                    "upload_date": info.get('upload_date', ''),
                    "description": info.get('description', ''),
                    "file_path": real_filepath,
                    "file_size": os.path.getsize(real_filepath) if os.path.exists(real_filepath) else 0,
                    "is_audio_only": prefer_audio_only
                }
        
        except InterruptedError as ie:
            logger.warning(f"Download interrupted: {ie}")
            return {
                "success": False,
                "error": "Download cancelled by user",
                "cancelled": True
            }
        except Exception as e:
            logger.error(f"Failed to download video from {url}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def download_playlist(self, url: str) -> List[Dict]:
        """Download all videos from a playlist using yt-dlp's native batching"""
        outtmpl = os.path.join(self.output_dir, "%(playlist)s", "%(title)s.%(ext)s")
        
        downloaded_files = []
        def ydl_hook(d: dict):
            if d.get('status') == 'finished':
                downloaded_files.append(d.get('filename'))

        ydl_opts = {
            # 只下载单个最佳格式，避免需要 ffmpeg 合并音视频
            'format': 'best',
            'outtmpl': outtmpl,
            # 如果需要合并，输出为 mp4
            'merge_output_format': 'mp4',
            'quiet': True,
            'extract_flat': False,
            'progress_hooks': [ydl_hook],
            # 禁用需要 ffmpeg 的功能
            'postprocessors': [],
        }
        
        results = []
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 直接统一下载整个 playlist，yt-dlp 内部会深度优化网络请求
                playlist_info = ydl.extract_info(url, download=True)
                
                if 'entries' in playlist_info:
                    for entry in playlist_info['entries']:
                        if not entry:
                            continue
                        
                        # 匹配当前 entry 对应的生成文件
                        expected_file = ydl.prepare_filename(entry)
                        base, _ = os.path.splitext(expected_file)
                        actual_file = f"{base}.mp4" if os.path.exists(f"{base}.mp4") else expected_file
                        
                        results.append({
                            "success": True,
                            "title": entry.get('title', 'Unknown'),
                            "duration": entry.get('duration', 0),
                            "file_path": actual_file,
                            "file_size": os.path.getsize(actual_file) if os.path.exists(actual_file) else 0
                        })
                return results
        
        except Exception as e:
            logger.error(f"Failed to download playlist: {e}")
            return [{"success": False, "error": str(e)}]