# Agentic coding
As we've explored AI-related topics in previous lessons, including AI agents and AI application design, it's worth noting that Agentic coding is a distinct concept that has recently emerged, and its connection to these topics is still being understood, but today we'll dive into this new technique that has surfaced in the developer world.

## Why it's on the radar today
Agentic coding has appeared on GitHub Trending, HN Hiring, and dev.to, indicating a growing interest in this emerging technique among developers and companies. This increased visibility suggests that Agentic coding is addressing a current need or solving a specific problem in the development landscape. As a result, understanding Agentic coding can provide developers with a competitive edge in the job market and help them stay up-to-date with the latest advancements in the field.

## What you'll learn
* The core principles of Agentic coding and how it differs from traditional coding approaches
* How to apply Agentic coding to real-world problems and scenarios
* The benefits and limitations of using Agentic coding in development projects
* How Agentic coding relates to other emerging technologies and trends

## Core ideas
Agentic coding is an approach that focuses on creating autonomous, self-organizing systems that can adapt and evolve over time. This is achieved by designing systems that are composed of individual agents, each with their own goals, behaviors, and interactions. These agents can be thought of as simple programs that operate independently, but collectively produce complex and emergent behavior. For example, consider a swarm of birds flying together, where each bird follows simple rules, such as "stay close to your neighbors" and "avoid collisions," but the resulting pattern of flight is complex and dynamic. In Agentic coding, developers design and implement these rules and interactions to create systems that can solve problems, learn, and adapt in a more autonomous and flexible way.

## Where it fits
Agentic coding can be applied to a wide range of domains, from artificial intelligence and machine learning to web development and cybersecurity. It can be used to create more resilient and adaptive systems, such as self-healing networks, autonomous vehicles, or smart homes. Developers can reach for Agentic coding when they need to create systems that can operate in complex, dynamic environments, or when they want to create more human-like interactions and interfaces.

## Do this in 5 minutes
To get a feel for Agentic coding, try running a simple agent-based simulation using a library like NetLogo. For example, you can create a simulation of a flock of birds using the following code:
```java
// Create a flock of 100 birds
create-turtles 100

// Set the rules for each bird
ask turtles [
  set heading random 360
  fd 1
  if [any? other turtles in-radius 5] [
    set heading towards one-of other turtles in-radius 5
  ]
]
```
Run this code and observe how the birds interact and move together. This simple example illustrates the basic principles of Agentic coding and can be a starting point for exploring more complex and realistic simulations.