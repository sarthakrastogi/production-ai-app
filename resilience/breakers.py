import pybreaker
import structlog

log = structlog.get_logger()


def _on_open(breaker, *args):
    log.warning("circuit_breaker_opened", breaker=breaker.name)


def _on_close(breaker, *args):
    log.info("circuit_breaker_closed", breaker=breaker.name)


def _on_half_open(breaker, *args):
    log.info("circuit_breaker_half_open", breaker=breaker.name)


rival_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    name="rival",
    listeners=[
        pybreaker.CircuitBreakerListener(),
    ],
)

pageindex_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=30,
    name="pageindex",
)

gptcache_breaker = pybreaker.CircuitBreaker(
    fail_max=10,
    reset_timeout=15,
    name="gptcache",
)
