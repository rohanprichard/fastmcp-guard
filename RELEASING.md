# Releasing fastmcp-guard

Publishing is automated with GitHub Actions and **PyPI Trusted Publishing**
(OIDC) — there are no API tokens or secrets to manage. Publishing a GitHub
Release builds the package and uploads it to PyPI.

- CI (`.github/workflows/ci.yml`) runs ruff + mypy + pytest on every push/PR.
- Publish (`.github/workflows/publish.yml`) runs when a GitHub Release is
  published, builds the sdist + wheel, `twine check`s them, and uploads to PyPI.

---

## One-time setup

You do this once. It connects your GitHub repo to the PyPI project so Actions can
publish without a token.

### 1. Create the GitHub `pypi` environment

In the repo: **Settings → Environments → New environment**, name it exactly
`pypi`. (The publish job references `environment: pypi`.) Optionally add a
"Required reviewers" protection rule so a human approves each publish.

### 2. Add the trusted publisher on PyPI

`fastmcp-guard` already exists on PyPI, so add the publisher to the existing
project:

1. Go to **https://pypi.org/manage/project/fastmcp-guard/settings/publishing/**
2. Under **Add a new publisher → GitHub**, enter:
   - **Owner:** `rohanprichard`
   - **Repository name:** `fastmcp-guard`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. Save.

> Brand-new project instead? Use the **pending publisher** form at
> https://pypi.org/manage/account/publishing/ with the same values — PyPI will
> create the project on the first successful publish.

That's it. No `PYPI_API_TOKEN` secret is needed.

---

## Cutting a release

1. **Bump the version.** Edit `__version__` in
   `src/fastmcp_guard/__init__.py` (this is the single source of truth —
   `pyproject.toml` reads it dynamically). PyPI rejects re-uploads, so every
   release needs a new version.
2. **Update `CHANGELOG.md`** with the changes.
3. **Commit and tag:**
   ```bash
   git commit -am "release: v0.3.0"
   git tag v0.3.0
   git push && git push --tags
   ```
4. **Create the GitHub Release:** repo → **Releases → Draft a new release** →
   choose the `v0.3.0` tag → generate notes → **Publish release**.
5. The **Publish to PyPI** workflow runs automatically. Watch it under the
   **Actions** tab. If you added a required reviewer to the `pypi` environment,
   approve the run when prompted.
6. **Verify:**
   ```bash
   pip install fastmcp-guard==0.3.0
   ```

---

## Testing the build locally

Before tagging, you can validate the artifacts exactly as CI does:

```bash
python -m pip install build twine
python -m build            # writes dist/*.whl and dist/*.tar.gz
twine check dist/*         # validates metadata + long description
```

## Optional: dry-run to TestPyPI

To rehearse without touching real PyPI, add a second trusted publisher on
https://test.pypi.org for this repo, then temporarily point the publish step at
it:

```yaml
      - name: Publish to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
```

Install from TestPyPI to confirm:

```bash
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ fastmcp-guard
```
