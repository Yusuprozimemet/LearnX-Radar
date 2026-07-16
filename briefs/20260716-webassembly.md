# WebAssembly
## Why it's on the radar today
WebAssembly has been gaining attention lately due to its increasing adoption in various industries, including its use in Firefox [4] and its potential for near-native speed and language-agnosticism [5]. Additionally, companies like Fastly and Sequent Tech are looking for developers with WebAssembly experience, indicating a growing demand for this skill [1, 2].

## What's being discussed
Currently, there is a lot of discussion around the practical applications of WebAssembly, including its use in production environments, such as Google Sheets and Figma [5]. The WebAssembly community is also exploring its potential for use in edge networks, serverless functions, and AI inference pipelines. Furthermore, the W3C ratification of Wasm 3.0 as a formal standard and the stability of WASI Preview 2 have contributed to the growing interest in WebAssembly [5].

## What you'll learn
* The basics of WebAssembly and its key properties
* How to use WebAssembly in a real-world scenario
* The benefits of using WebAssembly, including near-native speed and language-agnosticism

## Core ideas
WebAssembly is a compact binary instruction format designed to run inside a sandboxed virtual machine. This VM is embedded in every major browser, in standalone runtimes like Wasmtime, and on cloud platforms from Cloudflare Workers to AWS Lambda. One of the key properties of WebAssembly is its near-native speed, which allows it to run at 80-95% of native performance with no JIT warmup delay. This is achieved through the use of a binary format that is structured for fast parsing, unlike JavaScript that must be parsed and compiled on every load.

Another important aspect of WebAssembly is its language-agnosticism, which allows it to be used with a variety of programming languages, including Rust, C/C++, Go, Python, and AssemblyScript. This makes it an attractive option for developers who want to write high-performance code that can be run on a variety of platforms.

For example, Shopify uses WebAssembly to execute custom checkout rules compiled from Rust to Wasm at the CDN edge, serving millions of users every day [5]. This demonstrates the potential of WebAssembly for use in production environments.

## Where it fits
WebAssembly is a versatile technology that can be used in a variety of contexts, including web development, edge computing, and serverless functions. Its language-agnosticism and near-native speed make it an attractive option for developers who want to write high-performance code that can be run on a variety of platforms.

## Do this in 5 minutes
Try running the following command to install Wasmtime, a standalone runtime for WebAssembly:
```bash
curl https://wasmtime.dev/install.sh -sO - | sh
```
This will install Wasmtime on your system, allowing you to run WebAssembly code. You can then use the `wasmtime` command to run WebAssembly files.

## Sources
1. https://news.ycombinator.com/item?id=48748705
2. https://news.ycombinator.com/item?id=48749845
3. https://dev.to/hermestomagent/xai-open-sourced-grok-build-im-a-coding-agent-heres-what-i-found-1o9m
4. https://developer.puter.com/labs/firefox-wasm/
5. https://dev.to/moksh/webassembly-in-2026-a-practical-guide-to-wasm-and-wasi-for-modern-developers-3ogm