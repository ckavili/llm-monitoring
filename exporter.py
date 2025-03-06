import json
import time
import logging
from typing import Dict, Optional, Tuple
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from prometheus_client import start_http_server, Gauge, Counter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('llm_endpoint_monitor')

class EndpointMonitor:
    def __init__(self, config_file: str, port: int = 8000, check_interval: int = 30):
        self.port = port
        self.check_interval = check_interval
        self.endpoints = self._load_endpoints(config_file)
        self._setup_metrics()
        
    def _load_endpoints(self, config_file: str):
        """Load endpoint configurations from a JSON file."""
        with open(config_file, 'r') as f:
            endpoints = json.load(f)
        logger.info(f"Loaded {len(endpoints)} endpoint configurations")
        return endpoints
    
    def _setup_metrics(self):
        """Set up Prometheus metrics."""
        self.status_metric = Gauge("llm_endpoint_status", "Status of the LLM endpoint (1=up, 0=down)", ["name", "type"])
        self.latency_metric = Gauge("llm_endpoint_latency", "Response time in seconds", ["name", "type"])
        self.errors_metric = Counter("llm_endpoint_errors", "Number of errors encountered", ["name", "type", "error_type"])
        self.requests_metric = Counter("llm_endpoint_requests", "Number of requests made", ["name", "type"])
    
    def check_openai_endpoint(self, endpoint: Dict[str, str]) -> Tuple[bool, Optional[float], Optional[str]]:
        """Check an OpenAI-compatible endpoint."""
        client = OpenAI(api_key=endpoint['token'], base_url=endpoint['url'])
        
        try:
            start_time = time.time()
            response = client.chat.completions.create(
                model=endpoint['model'],
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            latency = time.time() - start_time
            return True, latency, None
        except RateLimitError:
            return True, None, "rate_limit"
        except APIConnectionError:
            return False, None, "connection"
        except APIError:
            return False, None, "api_error"
        except Exception as e:
            return False, None, "unknown"
    
    def check_endpoint_status(self) -> None:
        """Check the status of all configured endpoints."""
        for endpoint in self.endpoints:
            name, type_ = endpoint["model"], endpoint["type"]
            self.requests_metric.labels(name=name, type=type_).inc()
            
            status, latency, error_type = self.check_openai_endpoint(endpoint)
            
            self.status_metric.labels(name=name, type=type_).set(1 if status else 0)
            
            if latency is not None:
                self.latency_metric.labels(name=name, type=type_).set(latency)
            
            if error_type:
                self.errors_metric.labels(name=name, type=type_, error_type=error_type).inc()
    
    def run(self) -> None:
        """Run the monitoring service."""
        logger.info(f"Starting HTTP server on port {self.port}")
        start_http_server(self.port)
        
        logger.info(f"Starting endpoint monitoring with {self.check_interval}s interval")
        while True:
            try:
                self.check_endpoint_status()
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            time.sleep(self.check_interval)

if __name__ == "__main__":
    config_file = "/config/endpoints.json"
    port = 8000
    interval = 30
    monitor = EndpointMonitor(config_file=config_file, port=port, check_interval=interval)
    monitor.run()
