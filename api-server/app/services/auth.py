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

    async def get_management_token(self) -> str:
        """Get an access token for the Auth0 Management API."""
        if not self._management_token:
            # Log the configuration (without secrets)
            logger.info(f"Attempting to get management token from Auth0 domain: {self.domain}")
            logger.info(f"Management API Client ID: {self.client_id[:6]}..." if self.client_id else "Client ID not set")
            
            if not self.client_id or not self.client_secret:
                logger.error("Auth0 Management API credentials are not properly configured")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Auth0 Management API configuration is missing"
                )

            async with httpx.AsyncClient() as client:
                token_url = f"https://{self.domain}/oauth/token"
                payload = {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "audience": f"https://{self.domain}/api/v2/",
                    "grant_type": "client_credentials"
                }

                try:
                    response = await client.post(token_url, json=payload)
                    if response.status_code != 200:
                        logger.error(f"Failed to get management token. Status: {response.status_code}")
                        logger.error(f"Response: {response.text}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error authenticating with Auth0 Management API: {response.text}"
                        )
                    self._management_token = response.json()["access_token"]
                except Exception as e:
                    logger.error(f"Exception while getting management token: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to connect to Auth0 Management API"
                    )
        return self._management_token

    async def get_user_email_from_auth0(self, user_id: str) -> str:
        """Fetch user email from Auth0 Management API."""
        token = await self.get_management_token()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://{self.domain}/api/v2/users/{user_id}",
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
        
        # Debug information
        print("\nAuth0 Token Debug Information:")
        print("------------------------")
        print("Available claims in token payload:")
        for claim, value in payload.items():
            # Mask sensitive values
            if claim in ['sub', 'email']:
                print(f"  {claim}: [MASKED]")
            else:
                print(f"  {claim}: {value}")
        print("------------------------\n")
        
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
                email = await self.get_user_email_from_auth0(auth0_id)
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

        # Find user in database
        user = db.query(User).filter(User.email == email).first()
        
        # If user doesn't exist, create them
        if not user:
            user = User(
                email=email,
                auth0_id=auth0_id,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
        return user

auth_service = AuthService() 