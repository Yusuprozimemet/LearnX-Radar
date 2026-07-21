# AI coding agents

## Why it's on the radar today
AI coding agents have surfaced in the developer world today due to the increasing adoption of tools like Claude Code, OpenCode, and custom agents, as seen in GitHub Trending, HN Hiring, and dev.to [1]. This trend is driven by the need for faster software development and the potential of AI-powered coding agents to accelerate this process. Companies like Delta AI and We The Flywheel are already leveraging these agents to build and ship software quickly [3][4].

## What's being discussed
The current conversation around AI coding agents is focused on specific tools and techniques, such as Stoke, a kill switch for runaway AI agents [1]. Stoke is a Rust binary that enforces policy before any provider is called, offering features like hard budget caps, loop detection, and rate limiting. Other tools, like Agent Deck, a terminal session manager for AI coding agents, are also being discussed [2]. Additionally, companies are looking for engineers with experience in developing alongside AI coding agents, such as Claude Code and Cursor [4].

## What you'll learn
* How to use Stoke to enforce policy and prevent runaway AI agents
* How to integrate AI coding agents like Claude Code and OpenCode into development workflows
* How to manage and monitor AI-powered coding agents using tools like Agent Deck
* How to architect and own multi-step agent workflows
* How to track and manage costs associated with AI coding agents

## Core ideas
The key concept in AI coding agents is the ability to enforce policy and prevent runaway agents from incurring unnecessary costs. Stoke, for example, offers a simple and effective way to do this by sitting between the AI agent and the model provider. By enforcing hard budget caps, loop detection, and rate limiting, developers can prevent agents from retrying, looping, and fanning out on metered API keys. For instance, Stoke can be used to set a hard budget cap of $100 per API key, preventing agents from exceeding this limit and incurring unexpected costs [1].

## Where it fits
AI coding agents fit into the broader stack as a way to accelerate software development and improve productivity. They can be used in conjunction with other tools and techniques, such as DevOps and WebAssembly, to create a more efficient and effective development workflow. Developers can reach for AI coding agents when they need to automate repetitive tasks, generate code, or improve code quality.

## Do this in 5 minutes
To get hands-on with AI coding agents, try running the following command to install Agent Deck, a terminal session manager for AI coding agents:
```bash
git clone https://github.com/asheshgoplani/agent-deck.git
cd agent-deck
npm install
npm run start
```
This will give you a basic understanding of how Agent Deck works and how it can be used to manage AI coding agents.

## Sources
1. https://dev.to/pawfromoz/stoke-a-kill-switch-for-runaway-ai-agents-p0k
2. https://github.com/asheshgoplani/agent-deck
3. https://news.ycombinator.com/item?id=48749788
4. https://news.ycombinator.com/item?id=48747990
5. https://news.ycombinator.com/item?id=48749718