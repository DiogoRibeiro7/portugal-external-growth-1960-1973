# Security Policy

## Supported Versions

Security fixes are applied to the default branch until formal releases are introduced.

## Reporting a Vulnerability

Do not open a public issue for secrets, credentials, or private data exposure. Contact the repository owner directly and include:

- affected file, workflow, or command;
- steps to reproduce;
- whether any credential or non-public data may have been exposed.

## Secret Handling

Runtime credentials belong in `.env` or the local environment only. The repository redacts known API key values from persisted request metadata.
