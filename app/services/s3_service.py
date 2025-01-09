import os
import logging
from fastapi import HTTPException, UploadFile
import boto3
from botocore.exceptions import ClientError
from models import S3Config
from typing import Optional
from datetime import datetime
from uuid import uuid4
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class S3Handler:
    def __init__(self, config: S3Config):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            region_name=config.region_name
        )
        self.bucket_name = config.bucket_name

    async def upload_file(self, file: UploadFile, user_id: str) -> dict:
        """Upload a file to the raw-uploads directory in S3"""
        try:
            # Generate unique filename
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            unique_id = str(uuid4())[:8]
            extension = os.path.splitext(file.filename)[1]
            new_filename = f"{timestamp}-{unique_id}{extension}"

            # Define S3 path
            s3_path = f"raw-uploads/{user_id}/original-videos/{new_filename}"
            logger.info(f"S3 path: {s3_path}")

            # Upload file
            content = await file.read()
            await asyncio.to_thread(
                self.s3_client.put_object,
                Bucket=self.bucket_name,
                Key=s3_path,
                Body=content,
                ContentType=file.content_type
            )

            return {
                "file_path": s3_path,
                "filename": new_filename
            }

        except ClientError as e:
            logger.error(f"Error uploading to S3: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error uploading to S3: {str(e)}")

    async def copy_to_temp_processing(self, source_path: str, user_id: str) -> str:
        """Copy file from raw-uploads to temp-processing directory"""
        try:
            filename = source_path.split('/')[-1]
            temp_path = f"temp-processing/{user_id}/{filename}"
            
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': source_path
            }
            
            await asyncio.to_thread(
                self.s3_client.copy_object,
                Bucket=self.bucket_name,
                CopySource=copy_source,
                Key=temp_path
            )
            
            return temp_path
            
        except ClientError as e:
            logger.error(f"Error copying to temp processing: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def save_processed_content(self, temp_path: str, user_id: str) -> str:
        """Move processed content from temp to final directory"""
        try:
            filename = temp_path.split('/')[-1]
            final_path = f"processed-content/{user_id}/final-videos/{filename}"
            
            # Copy to final location
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': temp_path
            }
            
            await asyncio.to_thread(
                self.s3_client.copy_object,
                Bucket=self.bucket_name,
                CopySource=copy_source,
                Key=final_path
            )
            
            # Delete from temp location
            await asyncio.to_thread(
                self.s3_client.delete_object,
                Bucket=self.bucket_name,
                Key=temp_path
            )
            
            return final_path
            
        except ClientError as e:
            logger.error(f"Error saving processed content: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def generate_presigned_url(self, s3_path: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for accessing a file"""
        try:
            url = await asyncio.to_thread(
                self.s3_client.generate_presigned_url,
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_path
                },
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))