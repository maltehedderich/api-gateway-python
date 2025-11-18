You are a senior backend architect and Python engineer.

Create a detailed **Application Design Specification** in **Markdown format** for an **API Gateway** written in **Python**. The specification must describe the design only and explicitly **must not include any implementation code** (no code blocks, no pseudo-code, no function signatures).

### High-level Requirements

The API Gateway must provide:

1. **Request logging**

   - Log incoming requests and outgoing responses.
   - Capture metadata such as timestamp, method, path, status code, latency, client IP, correlation ID, and user/session identifiers when available.
   - Support configurable logging levels (e.g., error, info, debug).
   - Consider structured logging for downstream processing (e.g., JSON logs).

2. **Authorization via session cookies**

   - Use a session token mechanism for authenticating and authorizing requests.
   - Describe how session tokens are:
     - Issued
     - Validated
     - Refreshed (if applicable)
     - Revoked/expired
   - Specify how user permissions/roles are derived from the session token.
   - Define how invalid or missing tokens are handled and how error responses are returned.

3. **Rate limiting**

   - Define rate limiting strategies (e.g., per IP, per session token, per API key, or per route).
   - Describe how limits are configured (global vs per-route vs per-user).
   - Describe behavior when limits are exceeded (response codes, retry headers, etc.).
   - Discuss storage mechanism for rate limiting counters (in-memory, Redis, etc.) and trade-offs.

4. **Technology constraint**
   - Implementation will be in **Python**, but the document should focus only on **architecture and design**, not on actual implementation code.

### Structure and Level of Detail

Produce a **single Markdown document** with clear headings and subheadings. At minimum, include the following sections:

1. **Overview**

   - Brief description of the API Gateway’s purpose.
   - Scope of this design document.
   - Non-goals (what is explicitly out of scope).

2. **Architecture Overview**

   - High-level architecture description of the API Gateway.
   - Description of major components (e.g., HTTP server layer, routing, middleware chains, logging module, auth module, rate limiter, configuration, observability).
   - Interaction flow for a typical request (step-by-step).

3. **Request Flow**

   - Detailed description of the lifecycle of a request through the gateway:
     - Incoming connection handling.
     - Routing resolution.
     - Logging behavior at each stage.
     - Authentication and authorization using session tokens.
     - Rate limiting checks.
     - Upstream request forwarding.
     - Response handling and logging.
   - Describe error handling at each stage.

4. **Component Design**
   Break down the system into components and subcomponents. For each component, specify its responsibilities, inputs, outputs, and interactions.

   At minimum, include:

   - **HTTP Server & Routing**

     - How routes are defined and organized.
     - How middleware is composed and executed.
     - How versioning and path-based routing are handled.

   - **Logging Component**

     - What is logged and at which points.
     - Log structure (fields, formats).
     - Configurability (log level, sinks such as stdout/file/centralized logging).
     - Correlation IDs and tracing considerations.

   - **Session Token Authorization Component**

     - Session token format (high-level, e.g., opaque token vs signed token, not code).
     - Validation flow and trust model.
     - Lookup of user/session state.
     - Authorization rules evaluation (roles/permissions/policies).
     - Handling of expired or invalid tokens.
     - Security considerations (transport security, token leakage, storage).

   - **Rate Limiting Component**

     - Rate limiting algorithm(s) selected (e.g., token bucket, leaky bucket, fixed window, sliding window) and reasoning.
     - Keying strategy (by IP, user ID, session token, endpoint, etc.).
     - State storage (in-memory, Redis, etc.) and consistency/availability trade-offs.
     - Configuration model for limits.
     - Handling of limit exceed events and response format.
     - Operational concerns (reset intervals, burst vs sustained rates).

   - **Configuration & Environment**

     - How configuration is loaded (e.g., files, env vars, config service).
     - Configuration structure relevant to logging, auth, and rate limiting.
     - Support for different environments (dev, staging, prod).

   - **Observability & Metrics**
     - Metrics to expose (e.g., request counts, latencies, error rates, rate limiting events, auth failures).
     - Integration with monitoring systems (high-level).
     - Health checks and readiness/liveness endpoints.

5. **Data Models (Conceptual)**

   - Describe key conceptual data models (in plain language, not code), such as:
     - Request/response metadata.
     - Session token payload (e.g., user ID, roles, expiry).
     - Rate limiting counters/state.
   - Explain relationships between these models where relevant.

6. **Error Handling & Response Semantics**

   - Define standard error response structure (fields, format).
   - Define HTTP status codes used for:
     - Unauthorized/forbidden due to invalid/expired session tokens.
     - Rate limit exceeded.
     - Internal gateway errors.
   - Describe how errors are logged and how much detail is exposed to clients.

7. **Security Considerations**

   - Discuss security for:
     - Transport (TLS expectations).
     - Session token storage and transmission.
     - Protection against replay, brute-force or token guessing.
     - Logging of sensitive data (what must never be logged).
   - Mention any compliance or privacy considerations if relevant.

8. **Scalability and Performance**

   - Describe how the gateway can scale horizontally.
   - Discuss bottlenecks and how logging, authorization, and rate limiting affect performance.
   - Consider caching strategies where appropriate.

9. **Task Breakdown / Implementation Plan**

   - Provide a **task-based breakdown** of the work needed to implement this gateway in Python.
   - Use a structured list or hierarchy of tasks and subtasks.
   - For each task, include:
     - Short description.
     - Dependencies on other tasks if any.
   - Focus on **what** needs to be built, not **how** to write the code.

10. **Risks and Trade-offs**
    - Identify key technical risks and open questions.
    - Discuss trade-offs made (e.g., choice of rate limiting strategy, token format, storage solutions).

### Style and Constraints

- Output must be valid **Markdown**.
- Do **not** include any actual code, pseudo-code, or language-specific APIs.
- Focus on clarity, structure, and completeness of the **design** and **task breakdown**.
- Assume the reader is a professional Python/backend engineer who will use this document to implement the system.

Generate only the design specification document itself, starting directly with the title of the specification.
