import os
import unittest
import importlib.util

from web3.providers.rpc import HTTPProvider


def load_base_module():
    root = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(root, "src", "web3_scripts", "base.py")
    spec = importlib.util.spec_from_file_location("web3_scripts_base", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class TestGetW3(unittest.TestCase):
    def setUp(self):
        self.base = load_base_module()

    def test_single_url_uses_plain_http_provider(self):
        w3 = self.base.get_w3("https://eth.example.com")
        self.assertIsInstance(w3.provider, HTTPProvider)
        self.assertNotIsInstance(w3.provider, self.base.FallbackHTTPProvider)
        self.assertEqual(w3.provider.endpoint_uri, "https://eth.example.com")

    def test_multiple_urls_use_fallback_provider(self):
        w3 = self.base.get_w3(
            "https://a.example.com, https://b.example.com ,https://c.example.com"
        )
        self.assertIsInstance(w3.provider, self.base.FallbackHTTPProvider)
        self.assertEqual(len(w3.provider._providers), 3)
        self.assertEqual(
            [p.endpoint_uri for p in w3.provider._providers],
            [
                "https://a.example.com",
                "https://b.example.com",
                "https://c.example.com",
            ],
        )

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            self.base.get_w3("")

    def test_only_separators_raises(self):
        with self.assertRaises(ValueError):
            self.base.get_w3("  ,  ")


class TestFallbackHTTPProvider(unittest.TestCase):
    def setUp(self):
        self.base = load_base_module()

    def _make_provider(self):
        return self.base.FallbackHTTPProvider(
            ["https://a.example.com", "https://b.example.com"],
            retry_delay_seconds=0,
        )

    def test_fails_over_to_next_endpoint(self):
        provider = self._make_provider()

        class Failing:
            endpoint_uri = "https://a.example.com"

            def make_request(self, method, params):
                raise ConnectionError("boom")

        sentinel = {"jsonrpc": "2.0", "id": 1, "result": "0x1"}

        class Working:
            endpoint_uri = "https://b.example.com"

            def make_request(self, method, params):
                return sentinel

        provider._providers = [Failing(), Working()]

        result = provider.make_request("eth_blockNumber", [])
        self.assertIs(result, sentinel)
        self.assertEqual(provider.endpoint_uri, "https://b.example.com")

    def test_all_endpoints_failing_raises_without_leaking_urls(self):
        provider = self._make_provider()

        class Failing:
            endpoint_uri = "https://secret.example.com/api-key"

            def make_request(self, method, params):
                raise ConnectionError("boom")

        provider._providers = [Failing(), Failing()]

        with self.assertRaises(ConnectionError) as ctx:
            provider.make_request("eth_blockNumber", [])
        self.assertNotIn("secret.example.com", str(ctx.exception))

    def test_requires_at_least_one_endpoint(self):
        with self.assertRaises(ValueError):
            self.base.FallbackHTTPProvider(["  ", ""])

    def test_retry_schedule_and_delays(self):
        base = self.base
        calls = []
        delays = []
        logs = []

        class Recorder:
            def __init__(self, uri, succeed_on=None):
                self.endpoint_uri = uri
                self.succeed_on = succeed_on
                self.attempts = 0

            def make_request(self, method, params):
                self.attempts += 1
                calls.append(self.endpoint_uri)
                if self.succeed_on is not None and self.attempts >= self.succeed_on:
                    return {"result": self.endpoint_uri}
                raise ConnectionError("boom")

        # Defaults: 3 attempts per endpoint, 0.25s base delay, x2 backoff.
        provider = base.FallbackHTTPProvider(["https://a", "https://b"])
        first = Recorder("https://a")  # always fails -> exhausts all 3 attempts
        second = Recorder("https://b", succeed_on=1)  # succeeds on first attempt
        provider._providers = [first, second]

        original_sleep = base.time.sleep
        original_print = base.print_colored
        base.time.sleep = lambda seconds: delays.append(seconds)
        base.print_colored = lambda message, *args, **kwargs: logs.append(message)
        try:
            result = provider.make_request("eth_blockNumber", [])
        finally:
            base.time.sleep = original_sleep
            base.print_colored = original_print

        self.assertEqual(result, {"result": "https://b"})
        # try 0 x3 (backoff within endpoint), then immediate failover to try 1.
        self.assertEqual(calls, ["https://a", "https://a", "https://a", "https://b"])
        # Backoff applies only within endpoint a (0.25 -> 0.5); the switch to b
        # is immediate, and b succeeds on its first attempt (no wait).
        self.assertEqual(delays, [0.25, 0.5])
        # Every attempt except the very first logs the RPC index and attempt no.
        self.assertEqual(
            logs,
            [
                "Retrying with RPC #0, attempt 2...",
                "Retrying with RPC #0, attempt 3...",
                "Retrying with RPC #1, attempt 1...",
            ],
        )


if __name__ == "__main__":
    unittest.main()
