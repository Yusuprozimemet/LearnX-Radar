# WebAssembly
## Why it's on the radar today
WebAssembly has surfaced in the developer world today due to its increasing presence in job postings and articles related to AI, as seen on platforms like HN Hiring and dev.to. This surge in interest can be attributed to the technology's potential to enable faster and more efficient execution of code in web browsers, making it an attractive solution for applications that require high performance, such as AI and machine learning models. As a result, developers are now expected to have a basic understanding of WebAssembly and its applications.

## What you'll learn
* The core concepts and benefits of WebAssembly
* How WebAssembly differs from traditional JavaScript execution
* The role of WebAssembly in enabling high-performance web applications
* How to compile and run WebAssembly code
* The potential use cases for WebAssembly in AI and machine learning applications

## Core ideas
WebAssembly is a binary instruction format that allows code written in languages like C, C++, and Rust to be executed in web browsers, providing a significant performance boost compared to traditional JavaScript execution. The key idea behind WebAssembly is to provide a platform-agnostic, sandboxed environment for code execution, ensuring that the code runs securely and efficiently. This is achieved through the use of a binary format that can be compiled from various programming languages, allowing developers to write code in their language of choice and still run it in a web browser. For example, a developer can write a machine learning model in Python, compile it to WebAssembly, and then run it in a web browser, enabling fast and efficient execution of the model without the need for a native application.

## Where it fits
WebAssembly fits into the broader stack as a complement to JavaScript, enabling developers to write high-performance code that can be executed in web browsers. It is particularly useful for applications that require intense computations, such as AI, machine learning, and scientific simulations. Developers would reach for WebAssembly when they need to optimize the performance of their web applications, or when they want to run code written in languages other than JavaScript in a web browser.

## Do this in 5 minutes
To get hands-on with WebAssembly, open a terminal and run the following command to install the `wasm-pack` tool, which allows you to compile and package WebAssembly code:
```bash
cargo install wasm-pack
```
Then, create a new Rust project using `cargo new my_wasm_project`, and add the following code to the `src/lib.rs` file:
```rust
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
```
Finally, run `wasm-pack build` to compile the code to WebAssembly, and open the resulting `pkg` directory to see the compiled WebAssembly module. This will give you a basic understanding of how to compile and package WebAssembly code using Rust and `wasm-pack`.