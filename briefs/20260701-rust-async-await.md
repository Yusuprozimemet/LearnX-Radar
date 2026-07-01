# Rust async/await
## Why it's on the radar today
Rust async/await has been gaining attention due to its increasing adoption in modern web development, particularly in the context of building high-performance and concurrent systems. As seen in the dev.to articles, projects like euv [1] are leveraging Rust's async/await capabilities to build seamless interoperability between Rust and TypeScript.

## What's being discussed
The current conversation around Rust async/await revolves around its use in building modern web applications, with a focus on interoperability with other languages like TypeScript. Specifically, the use of `wasm-bindgen`, `js-sys`, and `web-sys` to enable seamless communication between Rust and TypeScript is being discussed [1]. Additionally, the article on euv highlights the importance of working with JavaScript promises and async in Rust [1].

## What you'll learn
* How to use Rust's async/await syntax to build concurrent systems
* How to leverage `wasm-bindgen`, `js-sys`, and `web-sys` for interoperability with TypeScript
* How to work with JavaScript promises and async in Rust

## Core ideas
Rust's async/await syntax allows developers to write concurrent code that is easier to read and maintain. The `async` keyword is used to define asynchronous functions, while the `await` keyword is used to suspend the execution of an asynchronous function until a value is available.

For example, consider the following code snippet:
```rust
async fn my_function() {
    let result = async_task().await;
    println!("Result: {}", result);
}
```
In this example, `my_function` is an asynchronous function that uses the `await` keyword to suspend its execution until the `async_task` function completes.

## Where it fits
Rust async/await is particularly useful when building high-performance and concurrent systems, such as web applications that require seamless communication between different languages.

## Do this in 5 minutes
Try running the following code snippet to see Rust's async/await syntax in action:
```rust
fn main() {
    async fn my_function() {
        println!("Hello from async function!");
    }

    let handle = tokio::spawn(my_function());
    handle.await.unwrap();
}
```
This code defines an asynchronous function `my_function` and uses the `tokio` crate to spawn it as a task. The `await` keyword is used to wait for the task to complete.

## Sources
1. https://dev.to/tengxgfyrz67s/typescript-interoperability-in-euv-4dbb
2. https://dev.to/ks_softech_/why-most-authentication-systems-are-still-vulnerable-in-2026-2lj9
3. https://dev.to/hashiravc/practical-modern-observability-fastapi-opentelemetry-prometheus-jaeger-and-grafana-46bj
4. https://dev.to/prosvirnin/can-you-build-observability-ingestion-on-s3-alone-no-kafka-no-disks-no-coordination-layer-11ib
5. https://dev.to/tengxgfyrz67s/cookie-and-session-management-in-hyperlane-1cja