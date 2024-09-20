
import inspect
import logging
from typing import Callable
from functools import wraps

DEFAULT_CONSECUTIVE_FAILURES_NUM = 5
DEFAULT_LOGGER_NAME = "ray.serve"

logger = logging.getLogger(DEFAULT_LOGGER_NAME)

class ModelService:
    # Methods can only be decorat directly, and cannot be used to decorat @fastAPI.xx. This decorator will not be invoked
    @staticmethod
    def consecutive_failure(_func = None, failures_num = DEFAULT_CONSECUTIVE_FAILURES_NUM) -> Callable:
        def decorator(method):
            is_async = inspect.iscoroutinefunction(method)
            logger.debug("method: {} is_async: {} failures_num: {}".format(method, is_async, failures_num))
            wrapper_func = None
            if is_async:
                @wraps(method)
                async def wrapper(self, *args, **kwargs):
                    logger.debug("async call: {} args: {} kwargs: {} self:{} ray_check_health:{}".format(method, args, kwargs, self, self._ray_check_health))
                    result = await method(self, *args, **kwargs)
                    return result
                wrapper_func = wrapper
            else:
                @wraps(method)
                def wrapper(self, *args, **kwargs):
                    logger.debug("call: {} args: {} kwargs: {} self:{} ray_check_health:{}".format(method, args, kwargs, self, self._ray_check_health))
                    result = method(self, *args, **kwargs)
                    return result
                wrapper_func = wrapper
            return wrapper_func
        return decorator(_func) if callable(_func) else decorator

    def __init__(self) -> None:
        # Mainly used in ray system health check
        self._ray_check_health: bool = True
        self._failure_message: str = ''

    def check_health(self):
        if not self._ray_check_health:
            raise RuntimeError(self.failure_message())
        
    def unhealth(self, message: str):
        self._ray_check_health = False
        self._failure_message = message

    def failure_message(self) -> str:
        return self._failure_message
    
    def is_health(self) -> bool:
        return self._ray_check_health

