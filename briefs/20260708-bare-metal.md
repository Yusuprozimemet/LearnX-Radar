# Bare Metal
## Why it's on the radar today
Bare Metal has surfaced in the developer world today as a required skill for a Senior Embedded Software Engineer position at phios.group, highlighting the demand for expertise in this area for embedded systems development [1].

## What's being discussed
The current conversation around Bare Metal is focused on its application in embedded systems, with specific mentions of Yocto and hybrid models [1]. Additionally, companies like Fastly are working on edge cloud platforms that involve low-level system programming, which may require Bare Metal expertise [4]. However, there is no specific debate or tension mentioned in the sources.

## What you'll learn
* The basics of Bare Metal programming and its application in embedded systems
* How to work with Yocto and hybrid models in Bare Metal development
* The role of Bare Metal in edge cloud platforms and low-level system programming

## Core ideas
Bare Metal programming involves writing code that directly interacts with the hardware, without the use of an operating system. This requires a deep understanding of the system's architecture and the ability to work with low-level programming languages like C and C++. In the context of embedded systems, Bare Metal programming is used to develop software that runs directly on the hardware, providing a high degree of control and efficiency.

For example, in a Yocto-based project, a developer might use Bare Metal programming to develop a custom device driver that interacts directly with the hardware. This would involve writing code in C or C++ that uses the Yocto API to access the hardware and perform the desired operations.

## Where it fits
Bare Metal programming is a specialized skill that is typically used in embedded systems development, where the need for low-level system programming and direct hardware interaction is critical. It is also used in edge cloud platforms, where the ability to optimize performance and efficiency at the hardware level is essential.

## Do this in 5 minutes
To get a feel for Bare Metal programming, try running a simple C program on a bare metal system using a tool like QEMU. You can use the following command to run a C program on a bare metal system:
```bash
qemu-system-x86_64 -kernel my_program
```
Replace "my_program" with the name of your C program, and make sure it is compiled to run on the x86-64 architecture. This will allow you to see how your program interacts with the hardware at a low level.

## Sources
1. https://news.ycombinator.com/item?id=48751313
2. https://news.ycombinator.com/item?id=48748008
3. https://news.ycombinator.com/item?id=48748468
4. https://news.ycombinator.com/item?id=48748705
5. https://news.ycombinator.com/item?id=48749995