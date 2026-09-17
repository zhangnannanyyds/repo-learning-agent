import unittest

from main import extract_retry_wait


class MainTests(unittest.TestCase):
    def test_extract_retry_wait(self) -> None:
        error = Exception("Please try again in 9h34m7.68s.")

        self.assertEqual("9h34m7.68s", extract_retry_wait(error))

    def test_extract_retry_wait_when_missing(self) -> None:
        error = Exception("rate limit reached")

        self.assertIsNone(extract_retry_wait(error))


if __name__ == "__main__":
    unittest.main(verbosity=2)
