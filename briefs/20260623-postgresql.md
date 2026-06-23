# PostgreSQL

## Why it's on the radar today
PostgreSQL has surfaced in recent discussions on platforms like dev.to and Hacker News, where developers are sharing their experiences with deploying applications using this database management system [1][2]. Specifically, a recent article on deploying a multi-module Spring Boot application to Render with PostgreSQL, Redis, Docker, and Flyway has highlighted the challenges and solutions involved in using PostgreSQL in a cloud-based setup [1]. Another article on building a self-hosted MLOps platform from scratch with FastAPI, PostgreSQL, GCS, and Docker has also showcased the use of PostgreSQL in a machine learning context [2].

## What's being discussed
Developers are currently discussing the use of PostgreSQL in conjunction with other tools like Docker, Flyway, and FastAPI to build scalable and efficient applications. For example, the use of PostgreSQL with Spring Boot and Hibernate/JPA is being explored, as well as its integration with Google Cloud Storage and GitHub Actions [1][2]. The Kimchi project, a self-hosted MLOps platform built with FastAPI, PostgreSQL, and Docker, is also being discussed as a example of how to build a production-style MLOps platform from scratch [2]. Some of the specific tools and techniques being discussed include:
* FastAPI and SQLAlchemy for building RESTful APIs and interacting with PostgreSQL databases
* Alembic and Flyway for managing database migrations
* Docker and Render for deploying and managing applications in the cloud

## What you'll learn
* How to deploy a Spring Boot application to Render with PostgreSQL and Docker
* How to build a self-hosted MLOps platform with FastAPI, PostgreSQL, and Docker
* How to use PostgreSQL with Hibernate/JPA and Spring Boot
* How to integrate PostgreSQL with Google Cloud Storage and GitHub Actions
* How to use Alembic and Flyway for database migration management

## Core ideas
PostgreSQL is a powerful open-source database management system that can be used to build scalable and efficient applications. When used with other tools like Docker, Flyway, and FastAPI, it can provide a robust and reliable platform for building and deploying applications. For example, the Kimchi project uses PostgreSQL as the primary database for storing model metadata, experiment results, and other data [2]. In a Spring Boot application, PostgreSQL can be used as the database backend, with Hibernate/JPA providing a layer of abstraction for interacting with the database [1]. To illustrate this, consider a simple example where a Spring Boot application uses PostgreSQL to store user data:
```java
@Entity
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private String name;
    private String email;
    // getters and setters
}
```
This example shows how a simple User entity can be defined using JPA annotations, with the `@Entity` annotation indicating that the class represents a database table.

## Where it fits
PostgreSQL is a fundamental component of many modern application stacks, particularly those that involve building scalable and efficient data-driven applications. It can be used in conjunction with a wide range of programming languages and frameworks, including Java, Python, and JavaScript. Developers may reach for PostgreSQL when building applications that require a robust and reliable database backend, such as e-commerce platforms, social media applications, or machine learning models.

## Do this in 5 minutes
To get hands-on experience with PostgreSQL, you can try running a simple Docker container with PostgreSQL and connecting to it using the `psql` command-line tool. First, pull the official PostgreSQL Docker image using the following command:
```bash
docker pull postgres
```
Then, run a new container using the following command:
```bash
docker run -d --name postgres -e POSTGRES_PASSWORD=mysecretpassword -p 5432:5432 postgres
```
Finally, connect to the database using the `psql` command-line tool:
```bash
psql -h localhost -p 5432 -U postgres
```
This will give you a basic PostgreSQL setup that you can use to experiment with and learn more about the database management system.

## Sources
1. https://dev.to/ojo_ilesanmi/deploying-a-multi-module-spring-boot-app-to-render-with-postgresql-redis-docker-and-flyway-4leb
2. https://dev.to/upshivam786/building-a-self-hosted-mlops-platform-from-scratch-with-fastapi-postgresql-gcs-and-docker-46i0
3. https://news.ycombinator.com/item?id=48357777
4. https://news.ycombinator.com/item?id=48357792
5. https://news.ycombinator.com/item?id=48357992