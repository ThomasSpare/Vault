import os
import platform
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class FFmpegConfig:
    def __init__(self):
        self.system = platform.system()
        self.ffmpeg_path = self._get_ffmpeg_path()
        
    def _get_ffmpeg_path(self):
        """Determine FFmpeg path based on operating system"""
        if self.system == "Windows":
            # Check common Windows paths
            possible_paths = [
                "C:/ffmpeg/bin/ffmpeg.exe",
                "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
                os.environ.get("FFMPEG_BINARY", "")
            ]
        else:
            # Linux/Mac paths
            possible_paths = [
                "/usr/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/opt/homebrew/bin/ffmpeg",
                os.environ.get("FFMPEG_BINARY", "")
            ]
            
        # Find first existing path
        for path in possible_paths:
            if path and Path(path).exists():
                logger.info(f"Found FFmpeg at: {path}")
                return path
                
        # If no path found, assume ffmpeg is in system PATH
        logger.warning("No explicit FFmpeg path found, using system PATH")
        return "ffmpeg"
    
    def configure_moviepy(self):
        """Configure MoviePy to use the correct FFmpeg binary"""
        os.environ["IMAGEMAGICK_BINARY"] = "convert"
        os.environ["FFMPEG_BINARY"] = self.ffmpeg_path
        
        # Verify FFmpeg is accessible
        import subprocess
        try:
            subprocess.run([self.ffmpeg_path, "-version"], 
                         capture_output=True, 
                         check=True)
            logger.info("FFmpeg configuration successful")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg configuration failed: {str(e)}")
            return False
