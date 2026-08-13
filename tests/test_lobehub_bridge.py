"""LobeHub message/file bridge tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gateway.runs.ingest import (
    FileRef,
    HttpxFileFetcher,
    IngestCache,
    IngestUrlPolicyError,
    LobeHubBridgeSettings,
    assert_ingest_url_allowed,
    ingest_file_refs,
    reset_ingest_cache_for_tests,
    select_ingest_files,
)
from gateway.runs.ingress import compose_run_question, parse_messages, prepare_run_from_messages
from lca.contracts.atoms.enums import StreamChannel
from lca.layer0_infra.file_store import LocalFileStore


class _StubFetcher:
    def __init__(self, payloads: dict[str, tuple[bytes, str]]) -> None:
        self._payloads = payloads

    async def fetch(self, url: str) -> tuple[bytes, str]:
        if url not in self._payloads:
            raise RuntimeError(f"missing stub for {url}")
        return self._payloads[url]


class TestLobeHubMessageParser(unittest.TestCase):
    def test_strips_available_tools_xml_from_history(self) -> None:
        messages = [
            {
                "role": "user",
                "content": (
                    '<available_tools description="x">\n'
                    '  <tool identifier="lobe-web-browsing" name="Web Browsing">search</tool>\n'
                    "</available_tools>\n\n你能做什么"
                ),
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "你能做什么")
        self.assertNotIn("available_tools", parsed.user_text)

    def test_strips_system_context_and_extracts_user_text(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "分析这个文件\n\n"
                            "<!-- SYSTEM CONTEXT (NOT PART OF USER QUERY) -->\n"
                            '<files_info><files><file id="f1" name="a.csv" '
                            'type="text/csv" size="10" url="http://x/a.csv"></file>'
                            "</files></files_info>\n"
                            "<!-- END SYSTEM CONTEXT -->"
                        ),
                    }
                ],
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "分析这个文件")
        self.assertEqual(len(parsed.file_refs), 1)
        self.assertEqual(parsed.file_refs[0].name, "a.csv")
        self.assertEqual(parsed.file_refs[0].url, "http://x/a.csv")

    def test_collects_first_class_files_on_the_wire(self) -> None:
        messages = [
            {
                "role": "user",
                "content": "分析一下这个文件",
                "files": [
                    {
                        "id": "f1",
                        "name": "report.xlsx",
                        "url": "http://minio/report.xlsx",
                        "mime_type": "application/vnd.ms-excel",
                        "size": 12,
                    }
                ],
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "分析一下这个文件")
        self.assertEqual(len(parsed.file_refs), 1)
        self.assertEqual(parsed.file_refs[0].name, "report.xlsx")
        self.assertEqual(parsed.file_refs[0].url, "http://minio/report.xlsx")
        self.assertEqual(parsed.file_refs[0].source, "files")

    def test_collects_image_list_on_the_wire(self) -> None:
        messages = [
            {
                "role": "user",
                "content": "看图",
                "imageList": [{"id": "img1", "alt": "chart", "url": "http://img.test/a.png"}],
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(len(parsed.file_refs), 1)
        self.assertEqual(parsed.file_refs[0].source, "imageList")
        self.assertEqual(parsed.file_refs[0].name, "chart")

    def test_collects_image_url_parts(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "http://img.test/chart.png"},
                    },
                ],
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "看图")
        self.assertEqual(len(parsed.file_refs), 1)
        self.assertEqual(parsed.file_refs[0].source, "image_url")

    def test_extracts_prior_turns_without_last_user(self) -> None:
        messages = [
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "收到"},
            {"role": "user", "content": "第二轮"},
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "第二轮")
        roles = [t.role for t in parsed.prior_turns]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertIn("第一轮", parsed.prior_turns[0].content)
        self.assertNotIn("第二轮", " ".join(t.content for t in parsed.prior_turns))

    def test_prior_turns_skip_empty_assistant(self) -> None:
        messages = [
            {"role": "user", "content": "今天有什么新闻"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "今天有什么新闻"},
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "今天有什么新闻")
        self.assertEqual(len(parsed.prior_turns), 1)
        self.assertEqual(parsed.prior_turns[0].role, "user")

    def test_strips_feedback_analysis_context_from_history(self) -> None:
        messages = [
            {
                "role": "user",
                "content": (
                    "<feedback_analysis_context>"
                    "<latest_assistant_reply><message role='assistant'>"
                    "<content></content></message></latest_assistant_reply>"
                    "</feedback_analysis_context>\n今天有什么新闻"
                ),
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "今天有什么新闻")
        self.assertNotIn("feedback_analysis_context", parsed.user_text)

    def test_unwraps_satisfaction_judge_envelope(self) -> None:
        """AgentSignal-style wrappers must not become the LCA objective."""
        messages = [
            {
                "role": "user",
                "content": (
                    "Judge the user's overall satisfaction.\n"
                    'message="分析这个自查表的内容"\n'
                    'serializedContext=""'
                ),
            }
        ]
        parsed = parse_messages(messages)
        self.assertEqual(parsed.user_text, "分析这个自查表的内容")
        self.assertNotIn("Judge", parsed.user_text)
        self.assertNotIn("serializedContext", parsed.user_text)


class TestLobeHubFileIngest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_ingest_cache_for_tests()

    def tearDown(self) -> None:
        reset_ingest_cache_for_tests()

    async def test_ingest_downloads_into_local_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(tmp))
            refs = (
                FileRef(name="data.csv", url="http://files.example/data.csv", mime_type="text/csv"),
            )
            fetcher = _StubFetcher({"http://files.example/data.csv": (b"a,b\n1,2", "text/csv")})
            result = await ingest_file_refs(refs, store, fetcher=fetcher)
            self.assertEqual(len(result.attachment_ids), 1)
            meta = store.get(result.attachment_ids[0])
            self.assertIsNotNone(meta)
            assert meta is not None
            self.assertEqual(meta.name, "data.csv")
            self.assertEqual(store.read_bytes(result.attachment_ids[0]), b"a,b\n1,2")

    async def test_ingest_data_uri(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(tmp))
            data_url = "data:text/plain;base64,YWJj"
            refs = (FileRef(name="x.txt", url=data_url, mime_type="text/plain"),)
            result = await ingest_file_refs(refs, store)
            self.assertEqual(len(result.attachment_ids), 1)
            self.assertEqual(store.read_bytes(result.attachment_ids[0]), b"abc")

    def test_select_respects_size_cap(self) -> None:
        big = FileRef(name="big.bin", url="http://x/big", size_bytes=200 * 1024 * 1024)
        ok = FileRef(name="ok.txt", url="http://x/ok", size_bytes=10)
        selected = select_ingest_files((big, ok))
        self.assertEqual([item.name for item in selected], ["ok.txt"])

    async def test_ingest_cache_reuses_attachment_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(tmp))
            cache = IngestCache(Path(tmp) / "cache.json", max_entries=10, store=store)
            ref = FileRef(
                name="data.csv",
                url="http://127.0.0.1/data.csv",
                mime_type="text/csv",
                lobehub_id="file-abc",
            )
            fetcher = _StubFetcher({"http://127.0.0.1/data.csv": (b"1,2", "text/csv")})
            settings = LobeHubBridgeSettings(ingest_allow_private_ip=True)
            first = await ingest_file_refs(
                (ref,), store, fetcher=fetcher, cache=cache, settings=settings
            )
            second = await ingest_file_refs(
                (ref,), store, fetcher=fetcher, cache=cache, settings=settings
            )
            self.assertEqual(len(first.attachment_ids), 1)
            self.assertEqual(second.attachment_ids, first.attachment_ids)


class TestIngestUrlPolicy(unittest.IsolatedAsyncioTestCase):
    def test_blocks_unknown_public_host_when_private_disabled(self) -> None:
        settings = LobeHubBridgeSettings(
            ingest_url_allowlist="localhost",
            ingest_allow_private_ip=False,
        )
        with self.assertRaises(IngestUrlPolicyError):
            assert_ingest_url_allowed("https://evil.example/file.csv", settings)

    def test_allows_private_ip_when_enabled(self) -> None:
        settings = LobeHubBridgeSettings(ingest_allow_private_ip=True, ingest_url_allowlist="")
        assert_ingest_url_allowed("http://10.0.0.5/object", settings)

    async def test_httpx_fetcher_enforces_policy(self) -> None:
        fetcher = HttpxFileFetcher(
            LobeHubBridgeSettings(ingest_allow_private_ip=False, ingest_url_allowlist="localhost")
        )
        with self.assertRaises(IngestUrlPolicyError):
            await fetcher.fetch("http://203.0.113.9/x")


class TestPrepareRunFromMessages(unittest.IsolatedAsyncioTestCase):
    async def test_end_to_end_question_and_attachment_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(tmp))
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "统计附件\n\n"
                                "<!-- SYSTEM CONTEXT -->\n"
                                '<file id="f1" name="nums.csv" type="text/csv" '
                                'size="8" url="http://files.example/nums.csv"></file>\n'
                                "<!-- END SYSTEM CONTEXT -->"
                            ),
                        }
                    ],
                }
            ]
            fetcher = _StubFetcher({"http://files.example/nums.csv": (b"1,2,3", "text/csv")})
            run_input = await prepare_run_from_messages(messages, store, fetcher=fetcher)
            self.assertIn("统计附件", run_input.question)
            self.assertIn("/mnt/data/nums.csv", run_input.question)
            self.assertEqual(len(run_input.attachment_ids), 1)

    async def test_compose_run_question_excludes_history_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(tmp))
            question = compose_run_question("继续", (), store)
            self.assertEqual(question, "继续")
            self.assertNotIn("[对话历史]", question)


class TestLiveTailKeepsEveryChannel(unittest.TestCase):
    """LiveTail does not filter. Decision vs answer is Transport's ignore table."""

    def test_both_channels_stay_on_the_tail(self) -> None:
        from gateway.runs.live import LiveTail
        from lca.contracts.models.observability.journal import RunScope, StampedEvent, StepTextDelta

        tail = LiveTail()
        scope = RunScope(trace_id="t", run_id="r")
        tail.on_event(
            StampedEvent(
                seq=1,
                ts=1.0,
                scope=scope,
                event=StepTextDelta(
                    step=0, text_delta="secret", channel=StreamChannel.DECISION.value
                ),
            )
        )
        tail.on_event(
            StampedEvent(
                seq=2,
                ts=2.0,
                scope=scope,
                event=StepTextDelta(step=0, text_delta="你好", channel=StreamChannel.ANSWER.value),
            )
        )
        self.assertEqual(tail.buffer_size, 2)
        self.assertEqual(tail.last_seq, 2)


if __name__ == "__main__":
    unittest.main()
