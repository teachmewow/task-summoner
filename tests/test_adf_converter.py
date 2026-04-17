"""Tests for the ADF models, factory, and markdown-to-ADF converter."""

import json

from task_summoner.tracker.adf import (
    Adf,
    AdfBulletList,
    AdfCodeBlock,
    AdfDocument,
    AdfHeading,
    AdfMark,
    AdfOrderedList,
    AdfParagraph,
    AdfRule,
    AdfText,
)
from task_summoner.tracker.adf_converter import markdown_to_adf, parse_inline
from task_summoner.tracker.message_tracker import MessageTag

# ═══════ Factory tests ═══════


class TestAdfFactory:
    def test_text(self):
        node = Adf.text("hello")
        assert node.text == "hello"
        assert node.marks is None

    def test_bold(self):
        node = Adf.bold("strong")
        assert node.text == "strong"
        assert node.marks == [AdfMark(type="strong")]

    def test_code(self):
        node = Adf.code("func()")
        assert node.marks == [AdfMark(type="code")]

    def test_link(self):
        node = Adf.link("click", "https://x.com")
        assert node.marks[0].type == "link"
        assert node.marks[0].attrs == {"href": "https://x.com"}

    def test_paragraph(self):
        para = Adf.paragraph("text", Adf.bold("bold"))
        assert isinstance(para, AdfParagraph)
        assert len(para.content) == 2
        assert para.content[0].text == "text"
        assert para.content[1].marks == [AdfMark(type="strong")]

    def test_paragraph_from_strings(self):
        para = Adf.paragraph("a", "b")
        assert all(isinstance(n, AdfText) for n in para.content)

    def test_heading(self):
        h = Adf.heading(2, "Title")
        assert isinstance(h, AdfHeading)
        assert h.attrs == {"level": 2}

    def test_bullet_list(self):
        bl = Adf.bullet_list([Adf.paragraph("item")])
        assert isinstance(bl, AdfBulletList)
        assert len(bl.content) == 1
        assert bl.content[0].content[0].content[0].text == "item"

    def test_ordered_list(self):
        ol = Adf.ordered_list([Adf.paragraph("first")])
        assert isinstance(ol, AdfOrderedList)

    def test_code_block_with_lang(self):
        cb = Adf.code_block("x = 1", "python")
        assert isinstance(cb, AdfCodeBlock)
        assert cb.attrs == {"language": "python"}

    def test_code_block_no_lang(self):
        cb = Adf.code_block("x = 1")
        assert cb.attrs is None

    def test_rule(self):
        assert isinstance(Adf.rule(), AdfRule)

    def test_doc(self):
        doc = Adf.doc(Adf.paragraph("hi"), Adf.rule())
        assert isinstance(doc, AdfDocument)
        assert len(doc.content) == 2


# ═══════ Document serialization ═══════


class TestAdfDocument:
    def test_to_json_basic(self):
        doc = Adf.doc(Adf.paragraph("hello"))
        data = json.loads(doc.to_json())
        assert data["version"] == 1
        assert data["type"] == "doc"
        assert data["content"][0]["type"] == "paragraph"

    def test_to_json_excludes_none(self):
        doc = Adf.doc(Adf.paragraph("text"))
        data = json.loads(doc.to_json())
        # marks=None should not appear
        text_node = data["content"][0]["content"][0]
        assert "marks" not in text_node

    def test_to_json_includes_marks_when_present(self):
        doc = Adf.doc(Adf.paragraph(Adf.bold("b")))
        data = json.loads(doc.to_json())
        text_node = data["content"][0]["content"][0]
        assert text_node["marks"] == [{"type": "strong"}]

    def test_to_json_link(self):
        doc = Adf.doc(Adf.paragraph(Adf.link("click", "https://x.com")))
        data = json.loads(doc.to_json())
        mark = data["content"][0]["content"][0]["marks"][0]
        assert mark["type"] == "link"
        assert mark["attrs"]["href"] == "https://x.com"

    def test_to_json_code_block_no_attrs(self):
        doc = Adf.doc(Adf.code_block("code"))
        data = json.loads(doc.to_json())
        assert "attrs" not in data["content"][0]


# ═══════ Inline parser ═══════


class TestParseInline:
    def test_plain_text(self):
        result = parse_inline("hello world")
        assert len(result) == 1
        assert result[0].text == "hello world"
        assert result[0].marks is None

    def test_bold(self):
        result = parse_inline("this is **bold** text")
        assert len(result) == 3
        assert result[1].text == "bold"
        assert result[1].marks == [AdfMark(type="strong")]

    def test_inline_code(self):
        result = parse_inline("use `func()` here")
        assert result[1].text == "func()"
        assert result[1].marks == [AdfMark(type="code")]

    def test_mixed(self):
        result = parse_inline("**bold** and `code`")
        assert result[0].marks[0].type == "strong"
        assert result[2].marks[0].type == "code"

    def test_empty(self):
        assert parse_inline("") == []


# ═══════ Markdown-to-ADF ═══════


class TestMarkdownToAdf:
    def test_empty(self):
        assert markdown_to_adf("") == []

    def test_paragraph(self):
        nodes = markdown_to_adf("Hello world")
        assert len(nodes) == 1
        assert isinstance(nodes[0], AdfParagraph)

    def test_heading_levels(self):
        nodes = markdown_to_adf("# H1\n## H2\n### H3\n#### H4")
        assert len(nodes) == 4
        for i, level in enumerate([1, 2, 3, 4]):
            assert isinstance(nodes[i], AdfHeading)
            assert nodes[i].attrs["level"] == level

    def test_heading_with_bold(self):
        nodes = markdown_to_adf("## **Bold** heading")
        h = nodes[0]
        assert isinstance(h, AdfHeading)
        assert any(t.marks and t.marks[0].type == "strong" for t in h.content)

    def test_bullet_list(self):
        nodes = markdown_to_adf("- item 1\n- item 2\n- item 3")
        assert len(nodes) == 1
        assert isinstance(nodes[0], AdfBulletList)
        assert len(nodes[0].content) == 3

    def test_ordered_list(self):
        nodes = markdown_to_adf("1. first\n2. second")
        assert isinstance(nodes[0], AdfOrderedList)
        assert len(nodes[0].content) == 2

    def test_code_block(self):
        nodes = markdown_to_adf("```python\ndef foo():\n    pass\n```")
        assert isinstance(nodes[0], AdfCodeBlock)
        assert nodes[0].attrs == {"language": "python"}
        assert nodes[0].content[0].text == "def foo():\n    pass"

    def test_code_block_no_lang(self):
        nodes = markdown_to_adf("```\nsome code\n```")
        assert isinstance(nodes[0], AdfCodeBlock)
        assert nodes[0].attrs is None

    def test_horizontal_rule(self):
        nodes = markdown_to_adf("above\n---\nbelow")
        assert len(nodes) == 3
        assert isinstance(nodes[1], AdfRule)

    def test_mixed(self):
        md = "## Plan\n\n- Step 1\n- Step 2\n\nSome text.\n\n```bash\necho hello\n```"
        nodes = markdown_to_adf(md)
        types = [type(n).__name__ for n in nodes]
        assert types == ["AdfHeading", "AdfBulletList", "AdfParagraph", "AdfCodeBlock"]

    def test_list_break_on_empty_line(self):
        nodes = markdown_to_adf("- a\n- b\n\nParagraph")
        assert isinstance(nodes[0], AdfBulletList)
        assert isinstance(nodes[1], AdfParagraph)

    def test_list_type_switch(self):
        nodes = markdown_to_adf("- bullet\n1. ordered")
        assert isinstance(nodes[0], AdfBulletList)
        assert isinstance(nodes[1], AdfOrderedList)

    def test_bold_in_list_item(self):
        nodes = markdown_to_adf("- **bold** item")
        item_para = nodes[0].content[0].content[0]
        assert any(t.marks and t.marks[0].type == "strong" for t in item_para.content)


# ═══════ MessageTag integration ═══════


class TestMessageTagAdf:
    def test_embed_in_adf(self):
        tag = MessageTag(ticket_key="T-1", state="test", short_id="abc12345")
        result = tag.embed_in_adf(Adf.paragraph("hello"))
        data = json.loads(result)
        assert data["version"] == 1
        assert len(data["content"]) == 2  # paragraph + tag
        assert "[ts:T-1:test:abc12345]" in data["content"][-1]["content"][0]["text"]

    def test_embed_nodes_in_adf(self):
        tag = MessageTag(ticket_key="T-1", state="test", short_id="abc12345")
        nodes = markdown_to_adf("## Title\n- item")
        result = tag.embed_nodes_in_adf(nodes, Adf.paragraph("approval"))
        data = json.loads(result)
        types = [n["type"] for n in data["content"]]
        assert "heading" in types
        assert "bulletList" in types
        # Last is bd tag, second-to-last is approval
        assert "[ts:T-1:test:abc12345]" in data["content"][-1]["content"][0]["text"]
        assert "approval" in data["content"][-2]["content"][0]["text"]
