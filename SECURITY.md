# Security

This project stores credentials in the operating system keychain via `keyring`.

## Safe usage

- do not commit local config files, databases, or captured payloads
- avoid pasting `passToken` values into shell history when possible
- treat leaked `passToken` values as compromised and rotate them

## Reporting issues

If you find a vulnerability or a secret leak, do not post the secret in a public GitHub issue. Share only the minimum details needed to reproduce the issue.
