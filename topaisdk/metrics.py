
import logging
import time
import asyncio
from typing import Dict, List, Union, Any, Optional

from pydantic import BaseModel
from scipy.special import softmax
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from ray import serve
import httpx

logger = logging.getLogger("ray.serve")


class LatencyMetricsCollector:
    """Collects and processes latency metrics."""
    
    def __init__(self, service_id: str, metric_server_url: Optional[str] = None, 
                 report_interval_seconds: int = 10):
        self.service_id = service_id
        self.metric_server_url = metric_server_url
        self.report_interval_seconds = report_interval_seconds
        
        # Store latency measurements
        self.request_latency_ms = []
        self.request_count = 0
        self.request_error_count = 0
        
        # Additional metadata
        self.replica_tag = None
        try:
            self.replica_tag = serve.get_replica_context().replica_tag
        except:
            self.replica_tag = f"replica-{hash(self)}"
            
        self.labels = {
            "service": service_id,
            "replica": self.replica_tag
        }
        
        # Background task for reporting
        self.running = False
        self.reporting_task = None
        
    async def start(self):
        """Start the metrics reporting loop."""
        if self.running:
            logger.warning("Metrics collector already running")
            return
            
        self.running = True
        self.reporting_task = asyncio.create_task(self._reporting_loop())
        logger.info(f"Started latency metrics reporting for {self.service_id}")
        
    async def stop(self):
        """Stop the metrics reporting loop."""
        if not self.running:
            return
            
        self.running = False
        if self.reporting_task:
            self.reporting_task.cancel()
            try:
                await self.reporting_task
            except asyncio.CancelledError:
                pass
                
    async def _reporting_loop(self):
        """Background task that reports metrics at regular intervals."""
        while self.running:
            try:
                await self.report_metrics()
                await asyncio.sleep(self.report_interval_seconds)
            except asyncio.CancelledError:
                logger.info("Latency reporting loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in latency reporting loop: {e}")
                await asyncio.sleep(1)
                
    async def report_metrics(self):
        """Generate and report latency metrics to the metrics server."""
        if not self.metric_server_url:
            logger.debug("No metrics server URL provided, skipping report")
            return
            
        logger.info(f"Reporting latency metrics for {self.service_id}")
        # Calculate latency statistics
        metrics_list = []
        current_time = int(time.time())
        
        # Only report if we have latency data
        if self.request_latency_ms:
            # Copy and clear the latency list to avoid race conditions
            latencies = self.request_latency_ms.copy()
            self.request_latency_ms = []
            
            # Report raw latency values for each request
            for i, latency in enumerate(latencies):
                metrics_list.append({
                    "value": latency,
                    "timestamp": current_time,
                    "labels": {**self.labels, "name": "request_latency", "unit": "ms", "request_id": f"req-{i}"}
                })
        
        # Always report requests per second and error rate
        local_request_count = self.request_count
        local_error_count = self.request_error_count
        self.request_count = 0
        self.request_error_count = 0

        if not metrics_list:
            logger.warning("No latency metrics to report")
            return
        
        # Request rate (normalized to per second)
        request_rate = local_request_count / self.report_interval_seconds
        error_rate = local_error_count / max(1, local_request_count)
        
        metrics_list.extend([
            {
                "value": request_rate,
                "timestamp": current_time,
                "labels": {**self.labels, "name": "request_rate", "unit": "rps"}
            },
            {
                "value": error_rate,
                "timestamp": current_time,
                "labels": {**self.labels, "name": "error_rate", "unit": "ratio"}
            }
        ])
        
        # Prepare the payload
        payload = {
            "service_id": self.service_id,
            "metrics": metrics_list,
            "metadata": {
                "replica": self.replica_tag,
                "reporter": self.service_id
            },
            "metrics_complete": False
        }
        
        # Send to metrics server
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.metric_server_url}/metrics",
                    json=payload,
                    timeout=5.0
                )
                if response.status_code != 200:
                    logger.error(f"Failed to report latency metrics: {response.status_code} {response.text}")
                else:
                    logger.debug(f"Reported {len(metrics_list)} latency metrics to {self.metric_server_url}")
        except Exception as e:
            logger.error(f"Error reporting latency metrics: {e}")
        logger.info(f"Reported {self.service_id} {len(metrics_list)} latency metrics to {self.metric_server_url} done, used {(time.time() - current_time) * 1000:.2f} ms")
            
    def add_latency_measurement(self, request_path: str, latency_ms: float, error: bool = False):
        """Add a latency measurement to the collector."""
        self.request_latency_ms.append(latency_ms)
        self.request_count += 1
        if error:
            self.request_error_count += 1


class LatencyMiddleware(BaseHTTPMiddleware):
    """Middleware to measure request latency."""
    
    def __init__(self, app, metrics_collector: LatencyMetricsCollector):
        super().__init__(app)
        self.metrics_collector = metrics_collector

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time_ms = (time.time() - start_time) * 1000
            
            # Record latency
            self.metrics_collector.add_latency_measurement(
                request_path=request.url.path,
                latency_ms=process_time_ms,
                error=False
            )
            
            # Add latency headers for debugging
            response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
            return response
            
        except Exception as e:
            process_time_ms = (time.time() - start_time) * 1000
            
            # Record error latency
            self.metrics_collector.add_latency_measurement(
                request_path=request.url.path,
                latency_ms=process_time_ms,
                error=True
            )
            
            # Re-raise the exception
            raise e


def setup_metrics_to_serve(serve, app: FastAPI, config: Dict[str, Any]):
    """
    Setup the metrics collector settings.
    
    Args:
        config: Dictionary containing configuration parameters

    example:
    setup_metrics_to_serve(serve, app, {
        "service_id": "intention-classifier",
        "metrics_server_url": "http://localhost:8000/metrics",
        "metrics_report_interval": 10
    })
    """
    service_id = config.get("service_id", None)
    if service_id is None:
        raise ValueError("setup_metrics_to_serve: service_id is required")

    metrics_server_url = config.get("metrics_server_url", None)
    if metrics_server_url is None:
        raise ValueError("metrics_server_url is required")
    
    # Shutdown existing metrics collector if it exists
    if hasattr(serve, "metrics_collector") and serve.metrics_collector:
        asyncio.create_task(serve.metrics_collector.stop())
        
    # Create new metrics collector
    serve.metrics_collector = LatencyMetricsCollector(
        service_id=service_id,
        metric_server_url=metrics_server_url,
        report_interval_seconds=config.get("metrics_report_interval", 10)
    )
    
    # Start metrics reporting if URL is provided
    if metrics_server_url:
        asyncio.create_task(serve.metrics_collector.start())
        
        # Add latency middleware to the app if not already added
        if not any(isinstance(m, LatencyMiddleware) for m in app.user_middleware):
            app.add_middleware(LatencyMiddleware, metrics_collector=serve.metrics_collector)
            logger.info("Added metrics (LatencyMiddleware) middleware to the FastAPI app")
