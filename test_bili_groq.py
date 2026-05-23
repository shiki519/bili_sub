import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

import bili_groq


class FakeRedirectResponse:
    def __init__(self, url):
        self.url = url

    def raise_for_status(self):
        return None


class BilibiliCanonicalUrlTests(unittest.TestCase):
    def test_resolves_b23_short_link_to_standard_video_url(self):
        runtime_config = {"proxy_url": "", "ytdlp_proxy_url": ""}
        fake_session = unittest.mock.Mock()
        fake_session.get.return_value = FakeRedirectResponse(
            "https://www.bilibili.com/video/BV1jB9XB1EeZ/?vd_source=abc&p=2"
        )

        with patch.object(bili_groq, "make_bilibili_session", return_value=fake_session):
            result = bili_groq.resolve_bilibili_canonical_url(
                "https://b23.tv/abc123", runtime_config
            )

        self.assertEqual(result, "https://www.bilibili.com/video/BV1jB9XB1EeZ/?p=2")
        fake_session.get.assert_called_once_with(
            "https://b23.tv/abc123", allow_redirects=True, timeout=20, proxies=None
        )

    def test_normalizes_existing_bilibili_video_url_without_tracking_query(self):
        result = bili_groq.resolve_bilibili_canonical_url(
            " https://www.bilibili.com/video/BV1jB9XB1EeZ/?vd_source=abc&p=3 ",
            {"proxy_url": "", "ytdlp_proxy_url": ""},
        )

        self.assertEqual(result, "https://www.bilibili.com/video/BV1jB9XB1EeZ/?p=3")

    def test_keeps_original_short_link_when_resolution_fails(self):
        runtime_config = {"proxy_url": "", "ytdlp_proxy_url": ""}
        fake_session = unittest.mock.Mock()
        fake_session.get.side_effect = requests.RequestException("network down")

        with patch.object(bili_groq, "make_bilibili_session", return_value=fake_session):
            result = bili_groq.resolve_bilibili_canonical_url(
                "https://b23.tv/fallback", runtime_config
            )

        self.assertEqual(result, "https://b23.tv/fallback")


class BilibiliMetadataOutputTests(unittest.TestCase):
    def test_builds_video_metadata_from_view_and_page_info(self):
        view_info = {
            "title": "Example Title",
            "author": "Example UP",
            "bvid": "BV1jB9XB1EeZ",
            "aid": "12345",
        }
        page_info = {"cid": "67890", "page": 2}

        metadata = bili_groq.build_video_metadata(
            view_info,
            page_info,
            original_url="https://b23.tv/abc123",
            canonical_url="https://www.bilibili.com/video/BV1jB9XB1EeZ/?p=2",
        )

        self.assertEqual(
            metadata,
            {
                "title": "Example Title",
                "author": "Example UP",
                "bvid": "BV1jB9XB1EeZ",
                "aid": "12345",
                "cid": "67890",
                "page": "2",
                "original_url": "https://b23.tv/abc123",
                "canonical_url": "https://www.bilibili.com/video/BV1jB9XB1EeZ/?p=2",
            },
        )

    def test_emit_artifacts_prints_video_metadata_fields(self):
        metadata = {
            "title": "Example Title",
            "author": "Example UP",
            "bvid": "BV1jB9XB1EeZ",
            "aid": "12345",
            "cid": "67890",
            "page": "2",
            "original_url": "https://b23.tv/abc123",
            "canonical_url": "https://www.bilibili.com/video/BV1jB9XB1EeZ/?p=2",
        }
        output = StringIO()

        with redirect_stdout(output):
            bili_groq.emit_artifacts(metadata=metadata)

        lines = output.getvalue().splitlines()
        self.assertIn("RESULT_TITLE=Example Title", lines)
        self.assertIn("RESULT_AUTHOR=Example UP", lines)
        self.assertIn("RESULT_BVID=BV1jB9XB1EeZ", lines)
        self.assertIn("RESULT_AID=12345", lines)
        self.assertIn("RESULT_CID=67890", lines)
        self.assertIn("RESULT_PAGE=2", lines)
        self.assertIn("RESULT_ORIGINAL_URL=https://b23.tv/abc123", lines)
        self.assertIn(
            "RESULT_CANONICAL_URL=https://www.bilibili.com/video/BV1jB9XB1EeZ/?p=2",
            lines,
        )


class DeepSeekDateContextTests(unittest.TestCase):
    def test_summary_system_message_injects_beijing_date_context(self):
        runtime_config = {
            "deepseek_api_key": "test-key",
            "deepseek_base_url": "https://api.deepseek.test",
            "deepseek_proxy_url": "",
            "deepseek_model": "deepseek-chat",
            "deepseek_retries": "1",
            "deepseek_timeout": "30",
        }
        captured_payloads = []
        fake_response = unittest.mock.Mock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "choices": [{"message": {"content": "summary ok"}}]
        }

        def fake_post(*args, **kwargs):
            captured_payloads.append(kwargs["json"])
            return fake_response

        output = StringIO()
        date_context = "当前日期：2026年05月23日，北京时间。"
        with patch.object(
            bili_groq,
            "get_beijing_date_context",
            return_value=date_context,
            create=True,
        ), patch.object(bili_groq.requests, "post", side_effect=fake_post), redirect_stdout(output):
            result = bili_groq.call_deepseek_summary(
                "2026年5月已经发生的事件",
                "请总结",
                runtime_config,
            )

        self.assertEqual(result, "summary ok")
        system_content = captured_payloads[0]["messages"][0]["content"]
        self.assertTrue(system_content.startswith(date_context + "\n"))
        self.assertIn(
            "判断过去、当前、未来时，必须以以上当前日期为准；不要根据模型自身知识截止时间判断当前年份。",
            system_content,
        )
        self.assertTrue(system_content.endswith("\n\n请总结"))
        self.assertIn(f"[summary] date context: {date_context}", output.getvalue())
        self.assertNotIn("2026年5月已经发生的事件", output.getvalue())


class PromptMigrationTests(unittest.TestCase):
    def test_load_prompt_file_falls_back_from_legacy_news_analysis_to_default(self):
        with TemporaryDirectory() as temp_dir:
            script_dir = Path(temp_dir)
            prompts_dir = script_dir / "prompts"
            prompts_dir.mkdir()
            default_prompt = "这是新的默认 prompt"
            (prompts_dir / "default.md").write_text(default_prompt, encoding="utf-8")

            output = StringIO()
            with patch.object(bili_groq, "SCRIPT_DIR", script_dir), redirect_stdout(output):
                loaded = bili_groq.load_prompt_file("prompts/news_analysis.md")

        self.assertEqual(loaded, default_prompt)
        self.assertIn(
            "[prompt] legacy prompt not found, fallback to prompts/default.md",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
