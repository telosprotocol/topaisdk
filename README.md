# topaisdk

## setup

```shell
pip install .
```


## Features

This SDK provides the following features for Ray Serve services:

- **Latency Metrics Collection**: Collects and reports request latency, request rate, and error rate.
- **Consecutive Failure Health Check**: Provides a decorator to add consecutive failure tracking and health check for model service methods.

## Usage

### Latency Metrics Collection

To collect latency metrics, you need to use the `setup_metrics_to_serve` function and the `LatencyMiddleware`.

First, import the necessary components:

```python
from topaisdk.metrics import setup_metrics_to_serve, LatencyMiddleware
from ray import serve
from fastapi import FastAPI
```

Then, in your Ray Serve application setup, call `setup_metrics_to_serve` and add `LatencyMiddleware` to your FastAPI app:

```python
app = FastAPI()
serve.init()

# Configure metrics
metrics_config = {
    "service_id": "your-service-name", # Replace with your service ID
    "metrics_server_url": "http://your-metrics-server:port/metrics", # Replace with your metrics server URL
    "metrics_report_interval": 10 # Reporting interval in seconds
}
setup_metrics_to_serve(serve, app, metrics_config)

# Add latency middleware
app.add_middleware(LatencyMiddleware, metrics_collector=serve.metrics_collector)

# Define your Ray Serve deployment
@serve.deployment()
@serve.ingress(app)
class MyModel:
    # Your model serving logic here
    pass

# Deploy your model
MyModel.deploy()
```

Ensure you have a metrics server running at the specified `metrics_server_url` to receive the reported metrics.

### Consecutive Failure Health Check

To use the consecutive failure health check, import the `ModelService` and use the `consecutive_failure` decorator on your model service methods.

```python
from topaisdk.modelservice import ModelService
from ray import serve

@serve.deployment()
class MyModelService(ModelService): # Inherit from ModelService
    def __init__(self):
        super().__init()
        # Your initialization

    @ModelService.consecutive_failure(max_failures_num=5) # Apply the decorator
    async def predict(self, input_data):
        # Your prediction logic
        # If this method raises exceptions consecutively for 5 times,
        # the service health check will fail.
        pass

    # Ray Serve health check method
    async def check_health(self):
        self.check_health() # This will raise an error if the service is unhealthy

# Deploy your service
MyModelService.deploy()
```

