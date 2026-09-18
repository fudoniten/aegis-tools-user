# Aegis User Tools

Self-service command-line tools for managing your personal encrypted secrets. Users can add environment variables and files that get deployed to their authorized hosts.

> **Status: the last mile does not work yet.** Everything in this repo does its
> job — `aegis-user` encrypts what you give it, and `aegis build user-secrets`
> in aegis-tools-system re-encrypts it per host. But the `aegis.secrets` NixOS
> module cannot currently decrypt the result, so nothing lands on a host. See
> [aegis/TODO.md](../aegis/TODO.md) for what is missing and who owns each half.
> Adding secrets now is safe and they will deploy once that is fixed.

## Installation

### NixOS (Recommended)

Add to your flake inputs:

```nix
{
  inputs = {
    aegis-tools-user.url = "github:fudoniten/aegis-tools-user";
  };
}
```

Then either:

1. **Add to home.packages (Home Manager):**
   ```nix
   home.packages = [ inputs.aegis-tools-user.packages.${system}.default ];
   ```

2. **Add to environment.systemPackages:**
   ```nix
   environment.systemPackages = [ inputs.aegis-tools-user.packages.${system}.default ];
   ```

3. **Run directly:**
   ```bash
   nix run github:fudoniten/aegis-tools-user -- --help
   ```

### Development

```bash
git clone https://github.com/fudoniten/aegis-tools-user
cd aegis-tools-user
nix develop
```

## Getting Started

### 1. Get Your Public Key

Your system administrator will run `aegis add-user <your-username>` and give you a public key. It looks like:

```
age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```

### 2. Create Your Secrets Repository

```bash
mkdir aegis-secrets-myusername
cd aegis-secrets-myusername
git init
```

### 3. Initialize with Your Key

```bash
aegis-user init --key=age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```

### 4. Add Your Secrets

```bash
# Add an environment variable
aegis-user add-env GITHUB_TOKEN ghp_xxxxxxxxxxxx

# Add a file
aegis-user add-file aws-creds ~/.aws/credentials

# Read secret from stdin (for sensitive values)
echo "my-secret-value" | aegis-user add-env MY_SECRET
```

### 5. Commit and Push

```bash
git add .
git commit -m "Add secrets"
git push
```

Your secrets will be deployed to your authorized hosts on the next `aegis build`.

## Usage

```bash
aegis-user --help
```

### Finding Your Repository

The `aegis-user` command needs to know where your secrets repository is. It checks:

1. **`AEGIS_USER` environment variable** - Set this to your repo path
2. **Current directory** - If it looks like a user secrets repo

If neither works, you'll see an error with instructions.

### Commands

```bash
# Initialize repo with public key from admin
aegis-user init --key=age1...
aegis-user init --key-file=./my-key.txt

# Add environment variables
aegis-user add-env NAME value
aegis-user add-env NAME --file=./secret.txt
echo "secret" | aegis-user add-env NAME

# Add files (any content -- certificates, keytabs, archives)
aegis-user add-file name /path/to/file

# List all secrets
aegis-user list

# Remove a secret
aegis-user remove NAME

# Show repo status
aegis-user status
```

`add-env` values are text — they end up as environment variables, so a
non-UTF-8 file is rejected with a pointer to `add-file`. `add-file` takes
arbitrary bytes and preserves them exactly, including trailing newlines.

`add-file` has no `--target`: a file secret is placed at
`/run/aegis/users/<username>/files/<name>` and nowhere else. There is no way to
ask for it in your home directory. The manifest format already carries `target`
and `mode` fields for this, but nothing populates them —
[aegis/TODO.md](../aegis/TODO.md) tracks it.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `AEGIS_USER` | Path to your aegis-secrets-USERNAME repository |

## Repository Structure

Your secrets repository will look like:

```
aegis-secrets-myusername/
├── .key                # Your public key
├── env/                # Encrypted environment variables
│   ├── GITHUB_TOKEN.age
│   └── OPENAI_API_KEY.age
└── files/              # Encrypted files
    └── aws-creds.age
```

## How It Works

1. You encrypt secrets with your public key using `aegis-user add-*`
2. Secrets are stored as `.age` files in your repo
3. The admin runs `aegis build-user-secrets` to:
   - Decrypt your secrets with the admin's copy of your private key
   - Re-encrypt them for each of your authorized hosts
4. On deployment, your hosts decrypt the secrets using their host master key
5. Secrets appear under `/run/aegis/users/<username>/` — `env/<NAME>` for
   environment variables, `files/<name>` for files
6. The `aegis.userSecrets` Home Manager module exports the `env/` entries as
   session variables

Steps 4-6 are not working today; see the status note at the top.

## Security Notes

- Your repository can be public - all files are encrypted
- Only your authorized hosts can decrypt the final secrets
- The admin holds an encrypted copy of your private key
- Never commit unencrypted secrets!

## See Also

- [aegis](../aegis) - NixOS modules for secret decryption
- [aegis-tools-system](../aegis-tools-system) - Admin CLI for building secrets
