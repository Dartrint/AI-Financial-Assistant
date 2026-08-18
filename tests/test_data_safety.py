import inspect
import unittest

from market_data.aggregator import DataAggregator


class TestDataSafety(unittest.TestCase):
    def test_mock_market_data_is_opt_in(self):
        self.assertFalse(inspect.signature(DataAggregator.fetch).parameters["use_mock_fallback"].default)
        self.assertFalse(inspect.signature(DataAggregator.fetch_multiple).parameters["use_mock_fallback"].default)
