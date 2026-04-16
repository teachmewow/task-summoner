"""Tests for the message tracker — bd tags in Jira comments."""

from __future__ import annotations

from board_dispatcher.tracker.message_tracker import (
    MessageTag,
    find_bd_comment,
    get_replies_after,
    is_bd_comment,
)


class TestMessageTag:
    def test_tag_format(self):
        tag = MessageTag(ticket_key="LLMOPS-42", state="planning", short_id="abc12345")
        assert tag.tag == "[bd:LLMOPS-42:planning:abc12345]"

    def test_tag_auto_id(self):
        tag = MessageTag(ticket_key="TEST-1", state="checking_doc")
        assert tag.tag.startswith("[bd:TEST-1:checking_doc:")
        assert len(tag.short_id) == 8

    def test_embed_in(self):
        tag = MessageTag(ticket_key="TEST-1", state="planning", short_id="aaa")
        result = tag.embed_in("Here is the plan.")
        assert "Here is the plan." in result
        assert "[bd:TEST-1:planning:aaa]" in result

    def test_unique_ids(self):
        t1 = MessageTag(ticket_key="TEST-1", state="a")
        t2 = MessageTag(ticket_key="TEST-1", state="a")
        assert t1.short_id != t2.short_id


class TestFindBdComment:
    def test_finds_correct_index(self):
        comments = [
            {"id": "1", "body": "hello"},
            {"id": "2", "body": "plan here [bd:TEST-1:planning:abc]"},
            {"id": "3", "body": "looks good"},
        ]
        assert find_bd_comment(comments, "[bd:TEST-1:planning:abc]") == 1

    def test_returns_none_if_not_found(self):
        comments = [{"id": "1", "body": "hello"}]
        assert find_bd_comment(comments, "[bd:TEST-1:planning:xyz]") is None

    def test_empty_comments(self):
        assert find_bd_comment([], "[bd:TEST-1:a:b]") is None


class TestIsBdComment:
    def test_detects_bd_comment(self):
        assert is_bd_comment({"body": "Plan [bd:TEST-1:planning:abc12345]"})

    def test_rejects_normal_comment(self):
        assert not is_bd_comment({"body": "lgtm"})
        assert not is_bd_comment({"body": ""})


class TestGetRepliesAfter:
    def test_returns_only_human_replies(self):
        tag = "[bd:TEST-1:planning:abc]"
        comments = [
            {"id": "1", "body": f"Plan posted {tag}"},
            {"id": "2", "body": "lgtm"},                              # human
            {"id": "3", "body": "Update [bd:TEST-1:fixing:def]"},      # agent
            {"id": "4", "body": "retry please"},                       # human
        ]
        replies = get_replies_after(comments, tag)
        assert len(replies) == 2
        assert replies[0]["body"] == "lgtm"
        assert replies[1]["body"] == "retry please"

    def test_no_replies(self):
        tag = "[bd:TEST-1:planning:abc]"
        comments = [{"id": "1", "body": f"Plan {tag}"}]
        assert get_replies_after(comments, tag) == []

    def test_tag_not_found(self):
        assert get_replies_after([{"id": "1", "body": "hi"}], "[bd:X:Y:Z]") == []
