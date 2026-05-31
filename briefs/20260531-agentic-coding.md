# Agentic coding
Having previously explored AI agent development, particularly in the context of the AI agent marketplace, we now turn our attention to a closely related yet distinct skill: Agentic coding, which has surfaced due to the emergence of agent-native platforms and concerns over agent cost governance.

## Why it's on the radar today
Agentic coding has appeared in GitHub Trending and dev.to, indicating a growing interest in this skill among developers. The rise of agent-native platforms has created a need for developers to understand how to effectively work with and govern agents, driving the demand for Agentic coding expertise. As a result, developers are now expected to have a solid grasp of Agentic coding principles to navigate this new landscape.

## What you'll learn
* The fundamentals of agent-oriented programming
* How to design and implement agentic systems
* Strategies for agent cost governance and optimization
* Best practices for integrating Agentic coding with existing development workflows

## Core ideas
Agentic coding revolves around the concept of agents, which are autonomous entities that can perceive their environment, make decisions, and take actions. In Agentic coding, developers create programs that can interact with these agents, influencing their behavior and decision-making processes. A key concept in Agentic coding is the idea of agent autonomy, where agents are designed to operate independently, making decisions based on their own goals and objectives. For example, consider a simple autonomous vehicle agent that must navigate through a city. The agent is programmed to follow traffic rules, avoid obstacles, and reach its destination, all while adapting to changing environmental conditions. By understanding how to design and interact with such agents, developers can create more sophisticated and adaptive systems.

## Where it fits
Agentic coding fits into the broader stack as a way to create more autonomous and adaptive systems. Developers would reach for Agentic coding when building applications that require complex decision-making, such as autonomous vehicles, smart home systems, or personalized recommendation engines. By leveraging Agentic coding, developers can create systems that can learn, adapt, and respond to changing conditions, making them more efficient, effective, and resilient.

## Do this in 5 minutes
To get hands-on with Agentic coding, open a Python interpreter and run the following code snippet:
```python
import random

class Agent:
    def __init__(self, name):
        self.name = name
        self.goals = []

    def add_goal(self, goal):
        self.goals.append(goal)

    def make_decision(self):
        goal = random.choice(self.goals)
        print(f"{self.name} has chosen to {goal}")

# Create an agent and add some goals
agent = Agent("MyAgent")
agent.add_goal("explore")
agent.add_goal("rest")

# Make a decision
agent.make_decision()
```
This simple example demonstrates the basic concept of an agent making decisions based on its goals. Run this code to see the agent in action, and start exploring the world of Agentic coding.