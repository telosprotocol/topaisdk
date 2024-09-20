
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
    def consecutive_failure(_func = None, max_failures_num = DEFAULT_CONSECUTIVE_FAILURES_NUM) -> Callable:
        def decorator(method):
            is_async = inspect.iscoroutinefunction(method)
            logger.debug("method: {} is_async: {} max_failures_num: {}".format(method, is_async, max_failures_num))
            wrapper_func = None
            method.max_failures_num = max_failures_num
            if is_async:
                @wraps(method)
                async def wrapper(self, *args, **kwargs):
                    call_success = True
                    logger.debug("async call: {} args: {} kwargs: {} self:{} ray_check_health:{}"
                                .format(method, args, kwargs, self, self._ray_check_health))
                    try:
                        result = await method(self, *args, **kwargs)
                        return result
                    except Exception as e:
                        self.update_health(method, str(e))
                        call_success = False
                        raise e
                    finally:
                        if call_success:
                            self.reset_health(method)
                        logger.debug('consecutive_failure consecutive_failure_map: {}'
                                     .format(self._consecutive_failure_map))
                wrapper_func = wrapper
            else:
                @wraps(method)
                def wrapper(self, *args, **kwargs):
                    call_success = True
                    logger.debug("call: {} args: {} kwargs: {} self:{} ray_check_health:{}"
                                 .format(method, args, kwargs, self, self._ray_check_health))
                    try:
                        result = method(self, *args, **kwargs)
                        return result
                    except Exception as e:
                        self.update_health(method, str(e))
                        call_success = False
                        raise e
                    finally:
                        if call_success:
                            self.reset_health(method)
                        logger.debug('consecutive_failure consecutive_failure_map: {}'
                                     .format(self._consecutive_failure_map))
                wrapper_func = wrapper
            return wrapper_func
        return decorator(_func) if callable(_func) else decorator

    def __init__(self) -> None:
        # Mainly used in ray system health check
        self._ray_check_health: bool = True
        self._failure_message: str = ''
        self._consecutive_failure_map = dict()

    def method_id(self, method) -> str:
        return "{}-{}".format(method.__name__, id(method))

    def reset_health(self, method) -> None:
        method_id = self.method_id(method)
        self._consecutive_failure_map[method_id] = 0

    def update_health(self, method, msg: str) -> None:
        method_id = self.method_id(method)
        if method_id not in self._consecutive_failure_map:
            self._consecutive_failure_map[method_id] = 0
        self._consecutive_failure_map[method_id] += 1
        if hasattr(method, 'max_failures_num'):
            max_failures_num = method.max_failures_num
        else:
            max_failures_num = DEFAULT_CONSECUTIVE_FAILURES_NUM
            logger.warning('{} no max_failures_num attr, use DEFAULT_CONSECUTIVE_FAILURES_NUM({})'
                           .format(method, DEFAULT_CONSECUTIVE_FAILURES_NUM))
        if self._consecutive_failure_map[method_id] >= max_failures_num:
            self.unhealth(msg)

    # ray system health check
    def check_health(self) -> None:
        if not self._ray_check_health:
            raise RuntimeError(self.failure_message())
        
    def unhealth(self, message: str) -> None:
        self._ray_check_health = False
        self._failure_message = message

    def failure_message(self) -> str:
        return self._failure_message
    
    def is_health(self) -> bool:
        return self._ray_check_health

