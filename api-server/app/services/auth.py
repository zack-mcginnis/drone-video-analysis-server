from typing import Optional
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
import logging
import secrets

logger = logging.getLogger(__name__)

security = HTTPBearer()

class AuthService:
    def __init__(self):
        self.domain = os.getenv("AUTH0_DOMAIN")
        self.audience = os.getenv("AUTH0_AUDIENCE")
        self.algorithms = ["RS256"]
        self._jwks = None
        self._management_token = None
        # Get Auth0 Management API credentials from environment
        self.client_id = os.getenv("AUTH0_CLIENT_ID")
        self.client_secret = os.getenv("AUTH0_CLIENT_SECRET")
        # Secret key for temporary tokens
        self.temp_token_secret = os.getenv("TEMP_TOKEN_SECRET", secrets.token_urlsafe(32))

    async def get_jwks(self) -> dict:
        if self._jwks is None:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"https://{self.domain}/.well-known/jwks.json")
                self._jwks = response.json()
        return self._jwks

    async def verify_token(self, token: str) -> dict:
        try:
            jwks = await self.get_jwks()
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "n": key["n"],
                        "e": key["e"]
                    }
                    break

            if not rsa_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=f"https://{self.domain}/"
            )
            
            return payload

        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_user_email_from_auth0(self, user_id: str, token: str) -> str:
        """Fetch user email from Auth0 Management API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{self.domain}/userinfo",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code != 200:
                logger.error(f"Failed to get user details: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error fetching user details from Auth0"
                )
            user_data = response.json()
            return user_data.get("email")

    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> User:
        
        token = credentials.credentials
        payload = await self.verify_token(token)
        
        # Get user ID from token
        auth0_id = payload.get("sub")
        if not auth0_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials - missing user ID",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Try to get email from token first
        email = payload.get("email")
        
        # If email not in token, try to get it from Auth0 Management API
        if not email:
            logger.info(f"Email not found in token, attempting to fetch from Auth0 Management API for user: {auth0_id}")
            try:
                email = await self.get_user_email_from_auth0(auth0_id, token)
            except Exception as e:
                logger.error(f"Error fetching user email from Auth0 Management API: {str(e)}")
                # Fall back to using the token's sub claim as the email
                logger.info("Falling back to using Auth0 ID as identifier")
                email = auth0_id

        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not retrieve user email",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # First, try to find user by auth0_id (which is unique)
        user = db.query(User).filter(User.auth0_id == auth0_id).first()
        
        # If not found by auth0_id, check by email as fallback
        if not user:
            user = db.query(User).filter(User.email == email).first()
        
        # If user doesn't exist, create them with retry logic for race conditions
        if not user:
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    # Check one more time in case user was created in another request
                    user = db.query(User).filter(User.auth0_id == auth0_id).first()
                    if user:
                        break
                        
                    user = User(
                        email=email,
                        auth0_id=auth0_id,
                        is_active=True
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                    break
                except Exception as e:
                    retry_count += 1
                    db.rollback()
                    logger.warning(f"Attempt {retry_count} failed to create user: {str(e)}")
                    if retry_count >= max_retries:
                        logger.error(f"Failed to create user after {max_retries} attempts: {str(e)}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to create user record"
                        )
                    # Small delay to prevent immediate retry
                    import asyncio
                    await asyncio.sleep(0.2)
            
        return user

    async def get_admin_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> User:
        """Get current user and verify they are an admin."""
        user = await self.get_current_user(credentials, db)
        
        if not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required for this action"
            )
            
        return user

    def create_temporary_token(self, data: dict, expires_delta: Optional[timedelta]) -> str:
        """
        Create a temporary JWT token for internal use (like HLS streaming).
        This token is NOT an Auth0 token and is only valid for internal services.
        
        Args:
            data: Dictionary of data to include in the token
            expires_delta: How long the token should be valid for, or None to use data's own exp
            
        Returns:
            JWT token string
        """
        try:
            to_encode = data.copy()
            
            # Only add expiration if expires_delta is provided and data doesn't already have an exp
            if expires_delta is not None and "exp" not in to_encode:
                expire = datetime.utcnow() + expires_delta
                to_encode.update({"exp": expire})
            
            logger.debug(f"Creating temporary token with data: {to_encode}")
            
            encoded_jwt = jwt.encode(
                to_encode,
                self.temp_token_secret,
                algorithm="HS256"  # Use HS256 for temporary tokens
            )
            
            logger.debug("Successfully created temporary token")
            return encoded_jwt
            
        except Exception as e:
            logger.error(f"Error creating temporary token: {str(e)}")
            raise
        
    def verify_temporary_token(self, token: str) -> dict:
        """
        Verify a temporary token created by create_temporary_token.
        
        Args:
            token: The JWT token to verify
            
        Returns:
            Dictionary of decoded token data
            
        Raises:
            HTTPException if token is invalid
        """
        if not token:
            logger.error("No token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No token provided",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        if not self.temp_token_secret:
            logger.error("No temporary token secret configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Token verification not configured",
            )
            
        try:
            logger.info(f"Verifying token: {token}")
            logger.info(f"Using secret (preview): {self.temp_token_secret[:10]}...")
            
            # First try to decode without verification to check structure
            try:
                unverified_header = jwt.get_unverified_header(token)
                logger.info(f"Token header: {unverified_header}")
                if unverified_header.get("alg") != "HS256":
                    raise ValueError(f"Invalid algorithm: {unverified_header.get('alg')}")
            except Exception as e:
                logger.error(f"Invalid token header: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token format",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Now verify the token
            payload = jwt.decode(
                token,
                self.temp_token_secret,
                algorithms=["HS256"]
            )
            
            logger.info(f"Token payload: {payload}")
            
            # Verify required claims
            if "user_id" not in payload:
                raise ValueError("Missing user_id claim")
            if "exp" not in payload:
                raise ValueError("Missing exp claim")
                
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.error("Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.JWTError as e:
            logger.error(f"JWT verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token signature",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except ValueError as e:
            logger.error(f"Invalid token claims: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"Unexpected error verifying token: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

auth_service = AuthService() 