# Agentic coding
## Why it's on the radar today

Agentic coding has recently gained attention in the developer community due to the emergence of agent-based software development. This approach is seen in various platforms, including GitHub Trending and dev.to, and is also mentioned in job postings on HN Hiring. The concept is closely related to LangChain, an AI Agent framework, which was previously discussed in the context of rising questions and AI Agent frameworks.

## What you'll learn

* The core concepts of agentic coding and its key characteristics
* How agentic coding differs from traditional AI-assisted coding tools
* The role of autonomous AI agents in planning, writing, testing, and modifying code
* The benefits and potential use cases of agentic coding in software development

## Core ideas

Agentic coding is a software development approach that involves autonomous AI agents planning, writing, testing, and modifying code with minimal human intervention. Unlike traditional AI-assisted coding tools, which wait for a user to type code or ask a question, agentic coding tools take a high-level instruction and execute it. These agents function more like a skilled contractor than a passive consultant, understanding the goal, breaking it down into steps, and executing the necessary actions to complete the work.

Agentic coding agents can navigate file systems, manage dependencies, and run terminal commands. If an agent writes code that causes an error, it can read the error message, reason through the problem, and apply a fix automatically. This shift from "chatting with AI" to "assigning tasks to AI" helps developers focus on architecture and logic while the agent handles implementation details.

For example, a developer might request an agentic coding agent to "Add authentication to the front end, update the API, and run tests." The agent would then read the relevant files, write code, run the tests, and deliver committed code.

## Where it fits

Agentic coding is part of a broader trend in software development, where AI-powered tools are becoming increasingly sophisticated and autonomous. As developers, we can expect to work alongside these tools, focusing on high-level tasks and letting the agents handle the implementation details.

Agentic coding can be used in a variety of scenarios, such as:

* Building new features or executing multi-file refactors
* Navigating unfamiliar codebases and understanding dependencies
* Developing across the whole codebase, including searching directories and tracing dependencies

## Do this in 5 minutes

Try out Claude Code, an agentic coding system developed by Anthropic. You can sign up for a free trial and explore the platform's capabilities. For example, you can ask Claude Code to "Write a simple Python script that prints 'Hello World' to the console." Observe how the agent reads the relevant files, writes code, and delivers committed code.

```python
# Claude Code example
import os

def write_hello_world_script():
    script = "#!/usr/bin/env python\nprint('Hello World')"
    with open("hello_world.py", "w") as f:
        f.write(script)
    os.system("python hello_world.py")

write_hello_world_script()
```

Note: This is a simplified example and may not work as-is in your environment. The goal is to demonstrate the concept of agentic coding, not to provide a working script.

## Sources
1. https://cloud.google.com/discover/what-is-agentic-coding
2. https://arxiv.org/html/2508.11126
3. https://www.ibm.com/think/topics/agentic-coding
4. https://www.anthropic.com/product/claude-code?r=0
5. https://agents-ui.com/blog/agentic-coding-developers-guide-autonomous-ai-agents/