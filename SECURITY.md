# Security Policy

## Reporting

Do not open a public issue containing credentials, private keys, host names, account names, remote paths, or unredacted logs. Report security-sensitive findings privately to the repository maintainers.

## Secret handling

PaperSim expects connection details and secrets to reside outside the repository in mode-`0600` files. The repository must not contain:

- passwords or 2FA secrets;
- private keys;
- gateway or cluster account identifiers;
- private host names or IP addresses;
- scheduler partitions tied to a private allocation;
- machine-specific absolute paths in physics code.

If a secret is committed, revoke or rotate it immediately before rewriting history.
