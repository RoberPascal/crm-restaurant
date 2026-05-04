from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
import structlog
import time

logger = structlog.get_logger(__name__)

class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования ошибок в production
    """
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Логируем только ошибки 4xx и 5xx
            if response.status_code >= 400:
                logger.warning(
                    "HTTP_ERROR_RESPONSE",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration=f"{duration:.3f}s",
                    client_ip=client_ip,
                    origin=request.headers.get('origin')
                )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "UNHANDLED_EXCEPTION",
                method=request.method,
                path=request.url.path,
                error=str(e),
                error_type=type(e).__name__,
                duration=f"{duration:.3f}s",
                client_ip=client_ip
            )
            # В production возвращаем общую ошибку
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )