import json
import time
import logging
from typing import Dict, Optional, Tuple
import requests
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
        
        # Add website-specific metrics using name
        self.website_status_metric = Gauge("website_status", "Status of the website (1=up, 0=down)", ["name"])
        self.website_latency_metric = Gauge("website_latency", "Response time in seconds for website", ["name"])
        self.website_errors_metric = Counter("website_errors", "Number of errors encountered for website", ["name", "error_type"])
        self.website_requests_metric = Counter("website_requests", "Number of requests made to website", ["name"])
    
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
            logger.info(f"Successfully checked OpenAI endpoint {endpoint['url']} - Latency: {latency:.3f}s")
            return True, latency, None
        except RateLimitError:
            return True, None, "rate_limit"
        except APIConnectionError:
            return False, None, "connection"
        except APIError:
            return False, None, "api_error"
        except Exception as e:
            return False, None, "unknown"
    
    def check_embedding_endpoint(self, endpoint: Dict[str, str]) -> Tuple[bool, Optional[float], Optional[str]]:
        """Check an embedding model endpoint."""
        headers = {
            "Authorization": f"Bearer {endpoint['token']}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": ["Test embedding request"],
            "model": endpoint["model"]
        }
        
        try:
            start_time = time.time()
            response = requests.post(f"{endpoint['url']}/embeddings", json=payload, headers=headers)
            latency = time.time() - start_time
            
            if response.status_code == 200:
                logger.info(f"Successfully checked embedding endpoint {endpoint['url']} - Latency: {latency:.3f}s")
                return True, latency, None
            else:
                logger.warning(f"Embedding endpoint {endpoint['url']} returned HTTP {response.status_code}")
                return False, None, f"http_{response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error while checking embedding endpoint {endpoint['url']}: {e}")
            return False, None, "connection"
    
    def check_vision_endpoint(self, endpoint: Dict[str, str]) -> Tuple[bool, Optional[float], Optional[str]]:
        """Check a vision model endpoint."""
        client = OpenAI(api_key=endpoint['token'], base_url=endpoint['url'])
        
        try:
            start_time = time.time()
            response = client.images.generate(prompt="a balloon cartoon style")
            latency = time.time() - start_time
            logger.info(f"Successfully checked vision endpoint {endpoint['url']} - Latency: {latency:.3f}s")
            return True, latency, None
        except APIError:
            return False, None, "api_error"
        except Exception as e:
            return False, None, "unknown"
    
    def check_website(self, endpoint: Dict[str, str]) -> Tuple[bool, Optional[float], Optional[str]]:
        """Check if a website is up and responsive."""
        url = endpoint['url']
        
        try:
            start_time = time.time()
            response = requests.get(url, timeout=10)
            latency = time.time() - start_time
            
            if response.status_code < 400:  # Consider 2xx and 3xx as "up"
                logger.info(f"Successfully checked website {url} - Latency: {latency:.3f}s")
                return True, latency, None
            else:
                logger.warning(f"Website {url} returned HTTP {response.status_code}")
                return False, None, f"http_{response.status_code}"
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error while checking website {url}")
            return False, None, "connection"
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while checking website {url}")
            return False, None, "timeout"
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking website {url}: {e}")
            return False, None, "request_error"
        except Exception as e:
            logger.error(f"Unknown error checking website {url}: {e}")
            return False, None, "unknown"
    
    def check_endpoint_status(self) -> None:
        """Check the status of all configured endpoints."""
        for endpoint in self.endpoints:
            type_ = endpoint["type"]
            
            if type_ == "website":
                # Ensure the endpoint has a name field
                if "name" not in endpoint:
                    logger.warning(f"Website endpoint {endpoint['url']} has no 'name' field - skipping")
                    continue
                
                name = endpoint["name"]
                self.website_requests_metric.labels(name=name).inc()
                
                status, latency, error_type = self.check_website(endpoint)
                
                self.website_status_metric.labels(name=name).set(1 if status else 0)
                
                if latency is not None:
                    self.website_latency_metric.labels(name=name).set(latency)
                
                if error_type:
                    self.website_errors_metric.labels(name=name, error_type=error_type).inc()
            else:
                # Handle regular LLM endpoints
                name = "nomic-embed-text-v1-5" if endpoint.get("model") == "/mnt/models" else endpoint.get("model", "unknown")
                self.requests_metric.labels(name=name, type=type_).inc()
                
                if type_ == "openai":
                    status, latency, error_type = self.check_openai_endpoint(endpoint)
                elif type_ == "embedding":
                    status, latency, error_type = self.check_embedding_endpoint(endpoint)
                elif type_ == "vision":
                    status, latency, error_type = self.check_vision_endpoint(endpoint)
                else:
                    status, latency, error_type = False, None, "unsupported_type"
                
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
    interval = 120
    monitor = EndpointMonitor(config_file=config_file, port=port, check_interval=interval)
    monitor.run()