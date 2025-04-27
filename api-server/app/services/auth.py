from typing import Optional
import os
from datetime import datetime
from jose import jwt, JWTError
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
import logging

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
        
        print("Getting current user")
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

auth_service = AuthService() 