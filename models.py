import os
# Ensure MoviePy uses the correct FFmpeg binary
ffmpeg_binary_path = "C:/ffmpeg/ffmpeg-2025-01-05-git-19c95ecbff-essentials_build/bin/ffmpeg.exe"
os.environ["FFMPEG_BINARY"] = ffmpeg_binary_path
from typing import List, Dict, Optional
from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from app.core.ffmpeg_config import FFmpegConfig
import torch
import logging
import tensorflow as tf
from PIL import Image
import numpy as np
from transformers import AutoFeatureExtractor, AutoModelForImageClassification
from moviepy.video.io.VideoFileClip import VideoFileClip
import librosa
import cv2


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class S3Config(BaseModel):
    bucket_name: str
    aws_access_key_id: str
    aws_secret_access_key: str
    region_name: str

class UploadResponse(BaseModel):
    status: str
    file_path: str
    temp_url: str

# Models and Config
class ContentConfig(BaseModel):
    content_types: List[str] = ["studio", "live", "daily", "creative"]
    style_presets: Dict[str, Dict] = {
        "studio": {"color_grade": "warm", "transition_style": "clean"},
        "live": {"color_grade": "vibrant", "transition_style": "energetic"},
        "daily": {"color_grade": "natural", "transition_style": "smooth"},
        "creative": {"color_grade": "moody", "transition_style": "dynamic"}
    }

class ContentProcessor:
    def __init__(self):
        # Initialize FFmpeg configuration
        ffmpeg_config = FFmpegConfig()
        if not ffmpeg_config.configure_moviepy():
            raise RuntimeError("Failed to configure FFmpeg")
            
        # Initialize AI models
        self.scene_detector = AutoModelForImageClassification.from_pretrained(
            "microsoft/resnet-50"  # Replace with your fine-tuned model
        )
        self.config = ContentConfig()
        self.feature_extractor = AutoFeatureExtractor.from_pretrained(
            "microsoft/resnet-50"  # Replace with your fine-tuned model
        )
        
        logger.info("ContentProcessor initialized successfully")
        
    async def detect_content_type(self, video_path: str) -> str:
        """Detect the type of content (studio, live, daily, creative)"""
        logger.info(f"Detecting content type for {video_path}")
        
        # Verify the file path
        if not os.path.exists(video_path):
            logger.error(f"File not found: {video_path}")
            raise FileNotFoundError(f"File not found: {video_path}")
        
        video = VideoFileClip(video_path)
        
        # Sample frames for analysis
        frames = []
        for t in np.linspace(0, video.duration, num=10):
            frame = video.get_frame(t)
            frames.append(frame)
        
        # Analyze frames for content type
        predictions = []
        for frame in frames:
            pred = self.analyze_frame(frame)
            predictions.append(pred)
            
        # Return most common prediction
        logger.info(f"Predictions: {predictions}")
        logger.info(f"Content type: {max(set(predictions), key=predictions.count)}")
        logger.info("Content type detection complete")
        return max(set(predictions), key=predictions.count)
    
    def analyze_frame(self, frame: np.ndarray) -> str:
        """Analyze a single frame to detect content type"""
        # Convert frame to PIL Image
        image = Image.fromarray(frame)
        
        # Predict scene type
        features = self.feature_extractor(image)
        prediction = self.scene_detector(features)
        
        return self.map_prediction_to_content_type(prediction)
    
    def analyze_audio(self, audio_path: str) -> dict:
        """Analyze audio characteristics"""
        y, sr = librosa.load(audio_path)
        
        # Extract audio features
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)
        
        return {
            "tempo": tempo,
            "spectral_centroids": spectral_centroids.mean()
        }
    
    async def process_content(self, 
                            video_path: str,
                            user_id: str,
                            user_preferences: dict = None) -> str:
        """Main content processing pipeline"""
        # Detect content type
        content_type = await self.detect_content_type(video_path)
        
        # Get base style preset
        style = self.config.style_presets[content_type].copy()
        
        # Modify style based on user preferences
        if user_preferences:
            style.update(user_preferences.get(content_type, {}))
        
        # Process video with style
        processed_path = self.apply_style(video_path, style)
        
        return processed_path
    
    def apply_style(self, video_path: str, style: dict) -> str:
        """Apply visual style to video"""
        video = VideoFileClip(video_path)
        
        # Apply color grading
        processed = self.apply_color_grade(video, style["color_grade"])
        
        # Apply transitions
        processed = self.apply_transitions(processed, style["transition_style"])
        
        # Save and return path
        output_path = f"processed_{video_path}"
        processed.write_videofile(output_path)
        
        return output_path

app = FastAPI()

content_processor = ContentProcessor()

@app.post("/processed-content/")
async def process_content(
    file: UploadFile = File(...),
    user_id: str = None,
    preferences: dict = None
):
    """API endpoint for content processing"""
    # Save uploaded file
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    video_path = os.path.join(upload_dir, file.filename)
    with open(video_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Process content
    processed_path = await content_processor.process_content(
        video_path,
        user_id,
        preferences or {}
    )
    
    return {"processed_file": processed_path}

# User Style Learning
class StyleLearner:
    def __init__(self):
        self.user_preferences = {}
    
    def update_preferences(self, user_id: str, content_type: str, 
                         feedback: dict):
        """Update user style preferences based on feedback"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {}
            
        current_prefs = self.user_preferences[user_id]
        
        # Update preferences based on feedback
        if content_type not in current_prefs:
            current_prefs[content_type] = feedback
        else:
            # Weighted update of preferences
            for key, value in feedback_items():
                if key in current_prefs[content_type]:
                    current_prefs[content_type][key] = (
                        0.7 * current_prefs[content_type][key] + 
                        0.3 * value
                    )
                else:
                    current_prefs[content_type][key] = value

    def get_preferences(self, user_id: str) -> dict:
        """Get learned preferences for a user"""
        return self.user_preferences.get(user_id, {})