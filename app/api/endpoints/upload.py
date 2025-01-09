import os
import boto3
import mimetypes
import asyncio
import logging
import platform
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from dotenv import load_dotenv
import logging
import aiofiles
import aiohttp
from typing import Dict, Any
from pathlib import Path


load_dotenv()  # Load environment variables from .env file
from app.services.s3_service import S3Handler
from app.core.config import settings
from models import S3Config, UploadResponse, ContentProcessor

logger = logging.getLogger(__name__)


local_dir = "/tmp/"
if not os.path.exists(local_dir):
    os.makedirs(local_dir)

router = APIRouter()

s3_config = S3Config(
    bucket_name=settings.AWS_BUCKET_NAME,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION
)
s3_handler = S3Handler(s3_config)
content_processor = ContentProcessor()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import requests

def get_temp_dir() -> str:
    """Get appropriate temporary directory based on operating system"""
    if platform.system() == "Windows":
        temp_dir = Path("C:/tmp/vault_processing")
    else:
        temp_dir = Path("/tmp/vault_processing")
    
    # Create directory if it doesn't exist
    temp_dir.mkdir(parents=True, exist_ok=True)
    return str(temp_dir)

async def verify_video_file(file_path: str) -> bool:
    """Verify if the video file is valid using ffmpeg"""
    import subprocess
    
    try:
        # Use ffprobe to check file validity
        result = subprocess.run([
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_type',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ], capture_output=True, text=True)
        
        return result.returncode == 0 and 'video' in result.stdout.lower()
    except Exception as e:
        logger.error(f"Error verifying video file: {str(e)}")
        return False

async def download_with_progress(url: str, destination: str) -> bool:
    """Download file with progress tracking and verification"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to download file: HTTP {response.status}")
                    return False
                
                # Ensure the directory exists
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                
                # Download the file
                async with aiofiles.open(destination, 'wb') as f:
                    while True:
                        chunk = await response.content.read(8192)  # 8KB chunks
                        if not chunk:
                            break
                        await f.write(chunk)
                
                # Verify file was downloaded completely
                if os.path.getsize(destination) == 0:
                    logger.error("Downloaded file is empty")
                    return False
                    
                return True
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return False

@router.post("/upload/", response_model=UploadResponse)
async def upload_content(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    """Upload endpoint that processes content directly in S3"""
    logger.info("Received upload request")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")

    # Validate file type
    allowed_types = ["video/mp4", "video/quicktime", "video/x-msvideo"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed"
        )

    try:
        # Step 1: Upload to raw-uploads directory
        logger.info("Uploading file to S3")
        upload_result = await s3_handler.upload_file(file, user_id)
        
        # Step 2: Copy to temp-processing directory
        logger.info("Copying to temp processing directory")
        temp_path = await s3_handler.copy_to_temp_processing(
            upload_result.get("file_path"),
            user_id
        )
        
        # Step 3: Process the content (this will be handled by your AI model)
        logger.info("Processing content")
        # Note: Your content_processor needs to be updated to work with S3 paths
        processed_temp_path = await content_processor.process_content(
            temp_path,
            user_id
        )
        
        # Step 4: Move to final processed-content directory
        logger.info("Saving processed content")
        final_path = await s3_handler.save_processed_content(
            processed_temp_path,
            user_id
        )
        
        # Generate a presigned URL for the processed content
        presigned_url = await s3_handler.generate_presigned_url(final_path)
        
        return {
            "status": "success",
            "file_path": final_path,
            "temp_url": presigned_url
        }

    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )



