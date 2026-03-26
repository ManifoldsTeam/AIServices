# AI DevKit Rules

## Project Context

This project uses ai-devkit for structured AI-assisted development. Phase documentation is located in `docs/ai/`.

## Documentation Structure

- `docs/ai/requirements/` - Problem understanding and requirements
- `docs/ai/design/` - System architecture and design decisions (include mermaid diagrams)
- `docs/ai/planning/` - Task breakdown and project planning
- `docs/ai/implementation/` - Implementation guides and notes
- `docs/ai/testing/` - Testing strategy and test cases
- `docs/ai/deployment/` - Deployment and infrastructure docs
- `docs/ai/monitoring/` - Monitoring and observability setup

## Code Style & Standards

- Follow the project's established code style and conventions
- Write clear, self-documenting code with meaningful variable names
- Add comments for complex logic or non-obvious decisions

### Configuration & Environment Variables (REQUIRED)

- **NEVER hard-code environment-specific values** (project IDs, bucket names, database names, API keys) in source code
- All configuration must come from environment variables via `src/config/settings.py`
- Use the `get_settings()` provider to access configuration values
- Environment files structure:
  - `.env` — Local selector only (`ENV=develop` or `ENV=product`)
  - `.env.develop` — Development environment values
  - `.env.product` — Production environment values
  - `.env.example` — Template (committed to git)
- Required fields in Settings class must NOT have default values (forces explicit configuration)

## Development Workflow

- Review phase documentation in `docs/ai/` before implementing features
- Keep requirements, design, and implementation docs updated as the project evolves
- Reference the planning doc for task breakdown and priorities
- Copy the testing template (`docs/ai/testing/README.md`) before creating feature-specific testing docs

### Timeline Tracking (REQUIRED)

After completing any significant action (bug fix, feature implementation, refactoring, data migration, infrastructure change), the agent **MUST** append a new entry to `docs/ai/timeline.md` following the template format defined in that file.

**What counts as "significant":**

- Code changes affecting core logic or architecture
- Data migrations (bucket uploads, database changes)
- Bug fixes that required investigation
- New features or endpoints deployed
- Configuration or infrastructure changes

**Entry must include:** Vấn đề (problem), Nguyên nhân (root cause), Hành động (actions taken), Kết quả (outcome), and References (files changed with descriptions).

### Checklist Verification & Documentation Updates (REQUIRED)

When verifying or completing checklist items from planning/implementation docs:

1. **Verify** the task/resource by running actual commands or inspecting the system
2. **Update** the corresponding documentation immediately after verification:
   - Mark checklist items as `[x]` with ✅ and verification date
   - Update configuration values to reflect actual verified values
   - Add "Verified YYYY-MM-DD" annotation to section headers
3. **Store** important configuration decisions in knowledge memory using `npx ai-devkit memory store`
4. **Sync** both language versions (EN + VN) if the project has bilingual docs

## AI Interaction Guidelines

- When implementing features, first check relevant phase documentation
- For new features, start with requirements clarification
- Update phase docs when significant changes or decisions are made

## Research & Information Gathering (REQUIRED)

**Use MCP Tools for Latest Information**

When working with external technologies, cloud services, APIs, or frameworks, you MUST use available MCP tools to research the latest information before making implementation decisions.

### When to Use MCP Research Tools

**MANDATORY for:**

- Setting up external services (GCP, AWS, Azure services)
- Checking API compatibility and availability
- Verifying model/service availability in specific regions
- Finding latest best practices for technologies (LangChain, LangGraph, etc.)
- Troubleshooting errors related to external services
- Checking pricing and quota information

**MCP Tools Available:**

- `mcp_tavily-search_tavily_research` - Deep research on technical topics
- `mcp_tavily-search_tavily_search` - Quick search for specific information
- `mcp_context7_get-library-docs` - Get latest library documentation
- `mcp_github_copilot_appmod-*` - Azure/cloud migration guidance

### Research Workflow

1. **Before Implementation**: Search for latest documentation and best practices
2. **During Setup**: Verify service availability and configuration requirements
3. **When Errors Occur**: Research error messages and known solutions
4. **Document Findings**: Store important discoveries in knowledge memory

### Example Usage

```bash
# When setting up GCP AI Search - Use MCP research
mcp_tavily-search_tavily_research: "Google Cloud Vertex AI Search Enterprise Edition setup 2026"

# When checking model availability
mcp_tavily-search_tavily_search: "Gemini 2.0 Flash availability asia-southeast1"

# Store findings
npx ai-devkit memory store \
  --title "GCP AI Search Enterprise Setup Steps" \
  --content "<research findings>" \
  --tags gcp,vertex-ai,search,setup
```

### Documentation Requirements

After using MCP tools for research:

1. **Create/Update** setup guides in `docs/ai/deployment/` with verified information
2. **Include** MCP research date and sources in documentation
3. **Update** implementation docs with actual verified configurations
4. **Store** critical findings in knowledge memory for team access

**Example Documentation Header:**

```markdown
> **Updated:** 2026-03-08  
> **MCP Research:** Tavily search for Vertex AI Search 2026 documentation
> **Verified:** Tested on project green-mercury-485016-n1
```

## Skills (Extend Your Capabilities)

Skills are packaged capabilities that teach you new competencies, patterns, and best practices. Check for installed skills in the project's skill directory and use them to enhance your work.

### Using Installed Skills

1. **Check for skills**: Look for `SKILL.md` files in the project's skill directory
2. **Read skill instructions**: Each skill contains detailed guidance on when and how to use it
3. **Apply skill knowledge**: Follow the patterns, commands, and best practices defined in the skill

### Key Installed Skills

- **memory**: Use AI DevKit's memory service via CLI commands when MCP is unavailable. Read the skill for detailed `memory store` and `memory search` command usage.

### When to Reference Skills

- Before implementing features that match a skill's domain
- When MCP tools are unavailable but skill provides CLI alternatives
- To follow established patterns and conventions defined in skills

## Knowledge Memory (Always Use When Helpful)

The AI assistant should proactively use knowledge memory throughout all interactions.

> **Tip**: If MCP is unavailable, use the **memory skill** for detailed CLI command reference.

### When to Search Memory

- Before starting any task, search for relevant project conventions, patterns, or decisions
- When you need clarification on how something was done before
- To check for existing solutions to similar problems
- To understand project-specific terminology or standards

**How to search**:

- Use `memory.searchKnowledge` MCP tool with relevant keywords, tags, and scope
- If MCP tools are unavailable, use `npx ai-devkit memory search` CLI command (see memory skill for details)
- Example: Search for "authentication patterns" when implementing auth features

### When to Store Memory

- After making important architectural or design decisions
- When discovering useful patterns or solutions worth reusing
- If the user explicitly asks to "remember this" or save guidance
- When you establish new conventions or standards for the project

**How to store**:

- Use `memory.storeKnowledge` MCP tool
- If MCP tools are unavailable, use `npx ai-devkit memory store` CLI command (see memory skill for details)
- Include clear title, detailed content, relevant tags, and appropriate scope
- Make knowledge specific and actionable, not generic advice

### Memory Best Practices

- **Be Proactive**: Search memory before asking the user repetitive questions
- **Be Specific**: Store knowledge that's actionable and reusable
- **Use Tags**: Tag knowledge appropriately for easy discovery (e.g., "api", "testing", "architecture")
- **Scope Appropriately**: Use `global` for general patterns, `project:<name>` for project-specific knowledge

## Testing & Quality

- Write tests alongside implementation
- Follow the testing strategy defined in `docs/ai/testing/`
- Use `/writing-test` to generate unit and integration tests targeting 100% coverage
- Ensure code passes all tests before considering it complete

### Notebook Testing Workflow (REQUIRED)

All integration tests and service validation MUST use Jupyter notebooks, NOT terminal one-liners.

**Notebook Organization:**

```
notebooks/
  tests/           — Integration test notebooks (service validation, pipeline tests)
  exploration/     — Experimental/exploratory notebooks (data analysis, prototyping)
```

**Rules:**

1. **Create proper test notebooks** with clear section headers and cell-by-cell validation
2. **Run cells one at a time** — code always has bugs, catch them early
3. **Never test with terminal one-liners** — notebooks provide reproducibility and visibility
4. **Each notebook**: setup → config verify → unit tests → integration tests → summary
5. **Naming convention**: `test_{service_name}.ipynb` for test notebooks
6. **Kernel**: Use the project conda environment (`AIservice`) for all notebooks
7. **Handle API response formats carefully** — e.g., `usage_metadata` may be a `dict` or object depending on the provider

### Known Technical Constraints

- **Vertex AI Search:** `VertexAISearchRetriever._serving_config` must be overridden with engine-level path (datastore-level path doesn't work). See `_apply_engine_serving_config()` in `vertex_search.py`.
- **Enterprise tier required:** Extractive answers only work with `SEARCH_TIER_ENTERPRISE`. Engine `gp-mathagent_1773042630372` already upgraded.
- **Per-model locations:** `gemini-3.1-flash-lite-preview` (review model) only available in `global` region. Use `REVIEW_MODEL_LOCATION=global` in `.env.develop`. Generation model uses `asia-southeast1`.
- **`gemini-3.1-flash-lite-preview` response format:** Returns parts with `thought_signature` — `response.content` is a list of parts, not a simple string.
- **LangChain deprecation:** `ChatVertexAI` deprecated in LangChain 3.2.0. Plan migration to `langchain-google-genai` / `ChatGoogleGenerativeAI`.

## Documentation

- Update phase documentation when requirements or design changes
- Keep inline code comments focused and relevant
- Document architectural decisions and their rationale
- Use mermaid diagrams for any architectural or data-flow visuals (update existing diagrams if needed)
- Record test coverage results and outstanding gaps in `docs/ai/testing/`

## Key Commands

When working on this project, you can run commands to:

- Understand project requirements and goals (`review-requirements`)
- Review architectural decisions (`review-design`)
- Plan and execute tasks (`execute-plan`)
- Verify implementation against design (`check-implementation`)
- Writing tests (`writing-test`)
- Perform structured code reviews (`code-review`)
