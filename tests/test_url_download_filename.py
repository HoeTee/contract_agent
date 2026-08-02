import unittest
from urllib.parse import quote

from endpoints.review.task_store import filename_from_content_disposition


class UrlDownloadFilenameTests(unittest.TestCase):
    def test_filename_star_decodes_utf8_docx_name(self):
        filename = "【已AI审查】合同.docx"
        header = f"attachment; filename*=UTF-8''{quote(filename)}"

        self.assertEqual(filename, filename_from_content_disposition(header))

    def test_filename_star_takes_precedence_over_filename(self):
        header = (
            "attachment; filename=\"fallback.docx\"; "
            "filename*=UTF-8''%E5%90%88%E5%90%8C.docx"
        )

        self.assertEqual("合同.docx", filename_from_content_disposition(header))

    def test_rejects_non_docx_filename(self):
        header = "attachment; filename=\"contract.pdf\""

        self.assertIsNone(filename_from_content_disposition(header))


if __name__ == "__main__":
    unittest.main()
