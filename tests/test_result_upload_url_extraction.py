import unittest

from endpoints.review.result_upload import ResultUploadError, extract_uploaded_url


class ResultUploadUrlExtractionTests(unittest.TestCase):
    def test_extract_uploaded_url_from_common_shapes(self):
        self.assertEqual(
            "https://example.com/a.docx",
            extract_uploaded_url({"url": "https://example.com/a.docx"}),
        )
        self.assertEqual(
            "https://example.com/b.docx",
            extract_uploaded_url({"data": {"fileUrl": "https://example.com/b.docx"}}),
        )
        self.assertEqual(
            "https://example.com/c.docx",
            extract_uploaded_url({"data": [{"downloadUrl": "https://example.com/c.docx"}]}),
        )

    def test_extract_uploaded_url_rejects_missing_url(self):
        with self.assertRaises(ResultUploadError):
            extract_uploaded_url({"data": [{"name": "a.docx"}]})


if __name__ == "__main__":
    unittest.main()
