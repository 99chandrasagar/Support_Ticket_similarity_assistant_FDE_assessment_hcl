# Dataset provenance

`tickets.json` and `new_tickets_example.json` are copied byte for byte from `starter_kit/data/` in the user-supplied `case-study-1-support-ticket-similarity.zip`. They contain 40 historical records and four incoming examples. They are synthetic assessment data, not real customer records.

The history supplies source ticket IDs, categories, tags, creation dates, resolved status, and resolution notes. It supplies no customer identities, access permissions, or resolution timestamps. Import assigns the fixed dataset namespace `solari-seed` and leaves resolution dates unknown.

SHA-256 checksums of the unchanged source files:

```text
tickets.json
b9ebbe875f313dea5c988b56e810f00540978532baae100861061c5f02b2c95a

new_tickets_example.json
d5225af6d299619b5b59877b0192621c2d213e6bf0603dc14b93287d092b4938
```

`evaluation_queries.json` contains locally authored relevance checks against this supplied history. It is not a provider answer key or independent held-out evaluation. The evaluator reads the four supplied incoming examples separately without changing them; their expected behavior is also a locally authored judgment.

Additional invented records used for tenant isolation and adversarial tests live under `tests/fixtures/`, never in the default history.
