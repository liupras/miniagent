#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-01-26
# @description: JWT authentication

import jwt  # pip install PyJWT
from loguru import logger
from datetime import datetime, timedelta,timezone
from typing import Optional, Dict

class JWTAuth:
    """JWT Authentication Management Class"""
    
    def __init__(self, secret_key: str = None, expire_days: int = None, algorithm: str = None):
        """
        Initialize JWT authentication
        
        :param secret_key: JWT key (read from configuration)
        :param expire_days: Token validity period (in days)
        :param algorithm: Encryption Algorithm
        """
        # Load from configuration (if no parameters are provided)
        if secret_key is None or expire_days is None or algorithm is None:
            from app.core.config import settings
            self.secret_key = secret_key or settings.jwt.secret_key
            self.expire_days = expire_days or settings.jwt.access_token_expire_days
            self.algorithm = algorithm or settings.jwt.algorithm
        else:
            self.secret_key = secret_key
            self.expire_days = expire_days
            self.algorithm = algorithm
        
        logger.debug(f"JWT Auth initialized - expire_days: {self.expire_days}, algorithm: {self.algorithm}")
    
    def create_token(self, username: str, token_type:str="access", expires_delta: Optional[timedelta] = None) -> str:
        """
        Create JWT token
        
        :param username: Username
        :param token_type: Type of the token (e.g., "access", "refresh")
        :param expires_delta: Expiration interval (optional)
        :return: JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(days=self.expire_days)
        
        # Calculate expiration time
        expire = datetime.now(timezone.utc) + expires_delta
        
        # build payload
        payload = {
            "sub": username,  # subject: username
            "exp": expire,    # expiration time
            "iat": datetime.now(timezone.utc),  # issued at
            "type": token_type  # token type
        }
        
        # create token
        try:
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            logger.debug(f"Token created for user: {username}, expires at: {expire}")
            return token
        except Exception as e:
            logger.error(f"Failed to create token: {str(e)}", exc_info=True)
            raise
    
    def verify_token(self, token: str) -> Optional[str]:
        """
        Verify JWT token (including expiration check)
        
        :param token: JWT token string
        :return: Username (if verification is successful); None (if verification fails or the application has expired)
        """
        try:
            # Decode and verify the token (PyJWT will automatically verify the expiration time).
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                options={
                    "verify_exp": True,  # Verify expiration time
                    "verify_signature": True  # Verify signature
                }
            )
            
            # Get Username
            username: str = payload.get("sub")
            
            if username is None:
                logger.warning("Token payload missing 'sub' field")
                return None
            
            logger.debug(f"Token verified for user: {username}")
            return username
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to verify token: {str(e)}", exc_info=True)
            return None
    
    def decode_token(self, token: str, verify: bool = False) -> Optional[Dict]:
        """
        decode JWT token
        
        :param token: JWT token string
        :param verify: Verify signature and expiration time. Default is False (only decode without verification)
        :return: payload dictionary (if successful); None (if decoding fails)
        """
        try:
            if verify:
                # Verify signature and expiration time
                payload = jwt.decode(
                    token, 
                    self.secret_key, 
                    algorithms=[self.algorithm]
                )
            else:
                # Decode only, do not verify (for debugging purposes)
                payload = jwt.decode(
                    token, 
                    options={"verify_signature": False}
                )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired during decode")
            return None
        except Exception as e:
            logger.error(f"Failed to decode token: {str(e)}", exc_info=True)
            return None
    
    def get_token_info(self, token: str) -> Dict:
        """
        Retrieve token information (including username and expiration time)
        
        :param token: JWT token string
        :return: token information dictionary
        """
        try:
            # Try verifying the token first. 
            payload = jwt.decode(
                token, 
                self.secret_key, 
                algorithms=[self.algorithm],
                options={"verify_exp": False}  # Do not verify expired information for now, in order to obtain information.
            )
            
            username = payload.get("sub")
            exp_timestamp = payload.get("exp")
            iat_timestamp = payload.get("iat")
            
            # Convert timestamps to a readable format
            exp_datetime = None
            if exp_timestamp:
                # First convert to naive datetime, then add the UTC time zone.
                exp_datetime = datetime.fromtimestamp(exp_timestamp).replace(tzinfo=timezone.utc)
            iat_datetime = None
            if iat_timestamp:
                iat_datetime = datetime.fromtimestamp(iat_timestamp).replace(tzinfo=timezone.utc)
            now_datetime = datetime.now(timezone.utc)
            
            # Check if it has expired
            is_expired = now_datetime > exp_datetime if exp_datetime else True
  
            def format_datetime(dt):
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if dt else None
            
            return {
                "username": username,
                "issued_at": format_datetime(iat_datetime),
                "expires_at": format_datetime(exp_datetime),
                "is_expired": is_expired,
                "valid": not is_expired
            }
            
        except jwt.InvalidTokenError:
            return {"error": "Invalid token", "valid": False}
        except Exception as e:
            logger.error(f"Failed to get token info: {str(e)}", exc_info=True)
            return {"error": str(e), "valid": False}


# Global instance
from app.core.config import settings
jwt_auth = JWTAuth(
    secret_key  = settings.jwt_secret_key,
    algorithm   = settings.jwt_algorithm,
    expire_days = settings.jwt_access_token_expire_days,
)
# example
if __name__ == "__main__":
   
    # Create token
    username = "user"
    token = jwt_auth.create_token(username)
    print(f"Token created: {token}")
    
    # verify token
    verified_username = jwt_auth.verify_token(token)
    print(f"Verified username: {verified_username}")
    
    """
    # get token information
    info = jwt_auth.get_token_info(token)
    print(f"Token info: {info}")
    
    # Test expired token
    import time
    print("\nTest expired token...")
    expired_jwt = JWTAuth() 
    expired_token = expired_jwt.create_token("test",expires_delta=timedelta(seconds=-1))  
    result = expired_jwt.verify_token(expired_token)
    print(f"Expired token verification result: {result}")  # It should be None
    
    # Invalid token test
    print("\nInvalid token test...")
    invalid_username = jwt_auth.verify_token("invalid_token_12345")
    print(f"Invalid token result: {invalid_username}")  # It should be None
    """