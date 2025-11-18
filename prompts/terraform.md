You are an expert Terraform and AWS cloud engineer.

You are given a repository that already contains an API Gateway, and your task is to design and implement a minimal, production-ready, cost-optimized AWS deployment using Terraform.

Goals and constraints:

Use fully managed, cloud‑native AWS services: API Gateway (HTTP API if possible), Lambda, DynamoDB (or S3 for static assets), CloudWatch Logs, and IAM. Prefer serverless over EC2, ECS, or RDS.

Target very low traffic / MVP scale and optimize strongly for cost:

Prefer on‑demand, pay‑per‑use (Lambda, DynamoDB on‑demand, HTTP API) and stay within Free Tier where reasonable.

Avoid unnecessary always‑on resources (no NAT gateways, no ALBs unless strictly required, no EKS).

Keep the architecture minimal:

Single AWS account and region.

One small VPC only if absolutely required; otherwise, keep Lambda functions public (no VPC).

One environment (e.g., dev or prod) parameterized via variables so more environments can be added later.

Terraform requirements:

Organize IaC into a small, clean module structure (modules/ + root) with clearly named resources, variables, and outputs.

Include:

API Gateway (HTTP API or REST, depending on repo), Lambda integrations, and minimal stages/routes.

IAM roles and least‑privilege policies for Lambdas and deployment.

DynamoDB tables or other persistence as required by the existing API, using on‑demand capacity and encryption by default.

CloudWatch Logs for API Gateway and Lambda with reasonable retention.

Optional custom domain + ACM certificate as a clearly separated, toggleable component.

Add sensible defaults, tags, and variables for: region, stage name, log retention, and cost‑sensitive settings.

Include basic Terraform documentation in README form: how to configure backend (can be local), required variables, and example terraform apply workflow.

Instructions:

Inspect the repository to infer API requirements (routes, methods, auth, persistence).

Propose a brief target architecture (1–2 paragraphs plus a small bullet list of components).

Implement the Terraform configuration following the constraints above.

Show the final directory structure and key Terraform files inline in the answer.

Highlight where the user must plug in repo‑specific values (e.g., Lambda build artifact paths, environment variables, DynamoDB table schema).
