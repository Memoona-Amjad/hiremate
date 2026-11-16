"""Deploy the backend to a Hugging Face Docker Space (free, no card needed).

One-time setup (in a terminal, from the repo folder):
    backend\\.venv\\Scripts\\pip install huggingface_hub
    backend\\.venv\\Scripts\\hf auth login        # paste a *Write* token from huggingface.co/settings/tokens

Deploy (run again any time to update):
    backend\\.venv\\Scripts\\python deploy\\deploy_hf.py

Then add the secret GEMINI_API_KEY once in the Space: Settings → Variables and secrets.
"""

from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SPACE_NAME = "hiremate-api"

# Non-secret settings (secrets like GEMINI_API_KEY are added by hand on the Space page).
VARIABLES = {
    "LLM_MODEL": "gemini-3.5-flash-lite",
    "LLM_FALLBACK_MODEL": "gemini-3.1-flash-lite",
    "RATE_LIMIT_PER_DAY": "10",
    "ALLOWED_ORIGINS": "http://localhost:3000",
}


def main() -> None:
    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{SPACE_NAME}"
    print(f"Deploying to https://huggingface.co/spaces/{repo_id}")

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    for key, value in VARIABLES.items():
        api.add_space_variable(repo_id, key, value)

    # Upload the backend code (never .env, the virtual env or caches).
    api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=ROOT / "backend",
        ignore_patterns=[".venv/*", ".env", "**/__pycache__/*", ".pytest_cache/*", "tests/*", "*.pyc"],
        commit_message="Deploy backend",
    )
    # The Space's README holds its settings (Docker SDK, port).
    api.upload_file(
        repo_id=repo_id,
        repo_type="space",
        path_or_fileobj=ROOT / "deploy" / "huggingface" / "README.md",
        path_in_repo="README.md",
        commit_message="Space settings",
    )

    host = repo_id.lower().replace("/", "-").replace("_", "-")
    print(f"Done. API URL (live after the build finishes): https://{host}.hf.space")


if __name__ == "__main__":
    main()
