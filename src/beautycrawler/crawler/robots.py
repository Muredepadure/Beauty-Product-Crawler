"""robots.txt parsing and matching per RFC 9309.

Replaces `urllib.robotparser`, which matches rule paths as plain prefixes (it ignores
the `*` and `$` wildcards most shops use, e.g. `Disallow: /*?sort=`) and keeps only the
first `User-agent: *` group when a file has several.

- A group is one or more `User-agent` lines followed by rules. All groups naming our
  product token (the User-Agent up to the first `/`, case-insensitive) are merged; if
  none does, all `*` groups are merged; with neither, everything is allowed.
- The longest matching `Allow`/`Disallow` pattern wins; on a tie `Allow` wins.
  `*` matches any characters, a trailing `$` anchors the end. Paths are compared
  percent-decoded, with the query string included.
- `Crawl-delay` (not in the RFC, but widely used) is read from the selected groups.
- `Sitemap` lines apply to the whole file.
"""

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True, slots=True)
class _Rule:
    allow: bool
    length: int  # length of the pattern as written; longer = more specific
    regex: re.Pattern[str]


@dataclass(slots=True)
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[_Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = unquote(pattern[:-1] if anchored else pattern)
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""), re.DOTALL)


def product_token(user_agent: str) -> str:
    """ "BeautyCrawler/0.1 (+https://…)" -> "beautycrawler"."""
    return re.split(r"[/\s]", user_agent.strip(), maxsplit=1)[0].lower()


class RobotsTxt:
    def __init__(self, groups: list[_Group], sitemaps: list[str]) -> None:
        self._groups = groups
        self.sitemaps = sitemaps

    @classmethod
    def parse(cls, text: str) -> "RobotsTxt":
        groups: list[_Group] = []
        sitemaps: list[str] = []
        current: _Group | None = None
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (s.strip() for s in line.split(":", 1))
            key = key.lower()
            if key == "sitemap":
                if value:
                    sitemaps.append(value)
            elif key == "user-agent":
                if current is None or in_rules:
                    current = _Group()
                    groups.append(current)
                    in_rules = False
                current.agents.append(value.lower())
            elif current is None:
                continue  # rules before any User-agent line belong to no group
            elif key in ("allow", "disallow"):
                in_rules = True
                if value:  # an empty Disallow allows everything: no rule
                    current.rules.append(_Rule(key == "allow", len(value), _compile(value)))
            elif key == "crawl-delay":
                in_rules = True
                try:
                    delay = float(value)
                except ValueError:
                    continue
                if delay >= 0:
                    current.crawl_delay = delay
        return cls(groups, sitemaps)

    def _selected(self, user_agent: str) -> list[_Group]:
        token = product_token(user_agent)
        named = [g for g in self._groups if token in g.agents]
        return named or [g for g in self._groups if "*" in g.agents]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (f"?{unquote(parts.query)}" if parts.query else "")
        if path == "/robots.txt":
            return True
        best: _Rule | None = None
        for group in self._selected(user_agent):
            for rule in group.rules:
                if not rule.regex.match(path):
                    continue
                if (
                    best is None
                    or rule.length > best.length
                    or (rule.length == best.length and rule.allow and not best.allow)
                ):
                    best = rule
        return best is None or best.allow

    def crawl_delay(self, user_agent: str) -> float | None:
        delays = [g.crawl_delay for g in self._selected(user_agent) if g.crawl_delay is not None]
        return max(delays) if delays else None
