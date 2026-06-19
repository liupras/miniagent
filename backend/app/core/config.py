#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-07
# @description: Configuration Management, using Pydantic Settings

from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application configuration class"""
    
    # ==================== Basic configuration ====================
    app_name: str = Field(default="MiniAgent", description="Application Name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=True, description="Debug mode")
    environment: str = Field(default="development", description="Operating environment")
    
    # ==================== API configuration ====================
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8088, description="API port")
    
    # ==================== Database configuration ====================
    sqlite_db_path: str = Field(default="./data/db/miniagent.db", description="SQLite database path")
    duck_db_path:str = Field(default="./data/db/duckdb.db", description="DuckDB database path")
    vector_db_path: str = Field(default="./data/vector", description="VectorDB data path")

    storage_dir: str = Field(default="./data/storage", description="Storage file dir")

    # ==================== BM25 configuration ====================
    bm25_index_path: str = Field(default="./data/bm25_index", description="BM25 index storage path")
    bm25_max_cache_size: int = Field(default=1000, description="Maximum cache size (number of items)")
        
    # ==================== Security Configuration ====================
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="CORS-allowed sources"
    )
    jwt_secret_key: str = Field(default=..., description="JWT Secret Key")
    jwt_access_token_expire_days: int = Field(default=90)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_days: int = Field(default=1, description="Access token expiration time (days)")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token expiration time (days)")   
    
    # ==================== Log configuration ====================
    log_level: str = Field(default="DEBUG", description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    log_dir: str = Field(default="../data/logs", description="Log directory")    
    
    # ==================== Performance Configuration ====================
    max_concurrent_requests: int = Field(default=10, description="Maximum concurrency")
    max_conversation_tokens: int = Field(default=4000, description="Maximum number of tokens in a single conversation")
    max_tool_calls: int = Field(default=5, description="Maximum number of tool calls")
    
    # Pydantic Settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Convert CORS source string to list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    def get_sqlite_path(self) -> Path:
        """Get the absolute path of the SQLite database"""
        base_dir = Path(__file__).parent.parent
        db_path = base_dir / self.sqlite_db_path
        # Ensure the directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path
    
    def get_duck_db_path(self) -> Path:
        """Get the absolute path of the duck database"""
        base_dir = Path(__file__).parent.parent
        db_path = base_dir / self.duck_db_path
        # Ensure the directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path
    
    def get_chroma_path(self) -> Path:
        """Get the absolute path of ChromaDB"""
        base_dir = Path(__file__).parent.parent
        chroma_path = base_dir / self.vector_db_path
        # Ensure the directory exists
        chroma_path.mkdir(parents=True, exist_ok=True)
        return chroma_path
    
    def get_log_dir(self) -> Path:
        """Get the absolute path of the log file"""
        base_dir = Path(__file__).parent.parent
        log_dir = base_dir / self.log_dir
        # Ensure the directory exists
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

# Global instance
settings = Settings()

def get_settings() -> Settings:
    """Obtain a configuration instance (for dependency injection)."""
    return settings


if __name__ == "__main__":
    # Test configuration loading
    print("=" * 50)
    print(f"Application Name: {settings.app_name}")
    print(f"Version: {settings.app_version}")
    print(f"Environment: {settings.environment}")
    print(f"SQLite path: {settings.get_sqlite_path()}")
    print(f"ChromaDB Path: {settings.get_chroma_path()}")
    print(f"CORS origin: {settings.cors_origins_list}")
    print("=" * 50)
