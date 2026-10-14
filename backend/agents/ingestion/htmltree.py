"""Small HTML tree for recorded listing pages. Stdlib only."""

from __future__ import annotations

from html.parser import HTMLParser

_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


class Node:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag = tag
        self.attrs = {key: value or "" for key, value in attrs}
        self.children: list[Node] = []
        self.text_parts: list[str] = []

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def text(self) -> str:
        chunks: list[str] = []

        def walk(node: Node) -> None:
            chunks.extend(node.text_parts)
            for child in node.children:
                walk(child)

        walk(self)
        return " ".join("".join(chunks).split())


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", [])
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, attrs)
        self._stack[-1].children.append(node)
        if tag not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._stack[-1].tag in {"script", "style"}:
            return
        self._stack[-1].text_parts.append(data)


def parse_document(html: str) -> Node:
    parser = _TreeParser()
    parser.feed(html)
    parser.close()
    return parser.root


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


def by_class(node: Node, class_name: str) -> list[Node]:
    return [item for item in walk(node) if class_name in item.classes]


def first_class(node: Node, class_name: str) -> Node | None:
    found = by_class(node, class_name)
    return found[0] if found else None


def text_of(node: Node | None) -> str | None:
    if node is None:
        return None
    text = node.text()
    return text or None


def paired_fields(node: Node) -> dict[str, str]:
    """Label/value rows: span.title + span.value, or dt/dd."""
    found: dict[str, str] = {}

    def add(key: str, value: str) -> None:
        cleaned = " ".join(key.split()).casefold().rstrip(":")
        body = " ".join(value.split())
        if cleaned and body and cleaned not in found:
            found[cleaned] = body

    def visit(current: Node) -> None:
        title = next((child for child in current.children if child.tag == "span" and "title" in child.classes), None)
        value = next((child for child in current.children if child.tag == "span" and "value" in child.classes), None)
        if title and value:
            add(title.text(), value.text())
        pending: str | None = None
        for child in current.children:
            if child.tag in {"dt", "th"}:
                pending = child.text()
                continue
            if child.tag in {"dd", "td"} and pending:
                add(pending, child.text())
                pending = None
                continue
            pending = None
            visit(child)

    visit(node)
    return found
