from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolContext:
    run_id: str
    chapter_id: str


@dataclass(frozen=True)
class ToolDescriptor:
    name: str
    enabled: bool = False
    description: str = ""


@dataclass
class ToolRegistry:
    tools: list[ToolDescriptor] = field(
        default_factory=lambda: [
            ToolDescriptor(
                name="future_web_search",
                enabled=False,
                description="Reserved tool slot for future web search, MCP, or skill integrations.",
            )
        ]
    )

    def available_tools(self, _context: ToolContext) -> list[ToolDescriptor]:
        return self.tools
