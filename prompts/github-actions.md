You are an expert DevOps engineer. Analyze this repository and propose a minimal set of GitHub Actions workflows that are practical and relevant, avoiding unnecessary or excessive automation.

Goals:

- Add only workflows that clearly support this project’s tech stack and use cases (e.g., build, test, lint, basic security checks, release/tag handling).
- Keep each workflow file short, readable, and focused on a single purpose.
- Use official or well-maintained actions where possible.
- Optimize for fast feedback and low resource usage (e.g., caching, matrix only when valuable).

Tasks:

1. Identify the project language, frameworks, and tooling from the repo.
2. Describe which workflows are worth adding and why (1–3 sentences each).
3. Generate the corresponding YAML files under .github/workflows with:
   - Clear, descriptive workflow and job names.
   - Triggers that match common development flows (e.g., pull_request, push to main).
   - Only essential steps and configuration.
4. Explain briefly how a maintainer can customize or extend each workflow if needed.

Return:

- A short overview of the chosen workflows.
- The complete YAML for each workflow file.
