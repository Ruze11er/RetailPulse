# Deploying RetailPulse

RetailPulse runs on **Streamlit Community Cloud** (free) at **https://retpulse.streamlit.app/**,
deployed from the GitHub repo `Ruze11er/RetailPulse`, branch `main`, entry point
`streamlit_app.py`.

## Settings at a glance

| Setting | Value | Why |
|---|---|---|
| Repository / branch | `Ruze11er/RetailPulse` / `main` | |
| Main file path | `streamlit_app.py` | Entry point at the repo root, so `retailpulse` imports without installing anything |
| Python version | **3.12** | Community Cloud's default, and tested in CI. **Changing it later means deleting and redeploying the app.** |
| Dependencies | `requirements.txt` (pinned) | Community Cloud uses the first dependency file it finds, and `requirements.txt` outranks `pyproject.toml`. Dev tools live in `requirements-dev.txt`, which the cloud ignores. |
| Secrets | none | The app has no API keys or credentials |
| Upload limit | 25 MB (`.streamlit/config.toml`) | Keeps the worst case within the free tier's memory |

## Pre-flight check (local)

Run from the repo root. All three must pass:

```bash
.venv/Scripts/python -m pytest -q        # includes the sample-data drift test
.venv/Scripts/python -m ruff check .
git status                               # no stray files you don't want published
```

What's been verified for this setup (October 2026):

- **Every pinned package has Linux wheels** for Python 3.12 and 3.14, so nothing compiles on the
  server. Checked with `pip download --only-binary=:all: --platform manylinux_2_28_x86_64`.
- **The full test suite passes on Python 3.12** (the deployed version) as well as 3.14 (local).
- **Memory:**
  - The app with the sample loaded and every page visited uses about **215 MB**.
  - The worst case, a 25 MB upload (about 340,000 rows), peaks at about **450 MB** for validation
    and analytics on top of Python's baseline, which is roughly **585 MB** in total.
  - Community Cloud gives an app 690 MB to 2.7 GB. Each visitor has their own in-memory database,
    so several people uploading large files at the same time could still hit the limit.

## Step 1: commit and push

```bash
git add -A
git commit -m "RetailPulse MVP"
git push -u origin main
```

Then open the **Actions** tab on GitHub. The **CI** workflow should go green on Python 3.12 and 3.14.

## Step 2: deploy on Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub. Authorise
   Streamlit to read your repositories if asked.
2. Click **Create app**, then **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `Ruze11er/RetailPulse`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **App URL:** pick a subdomain, e.g. `retailpulse-demo` (gives `retailpulse-demo.streamlit.app`)
4. Open **Advanced settings**, choose **Python 3.12**, and leave Secrets empty. Click **Save**.
5. Click **Deploy**. The first build takes a few minutes while packages install. Watch the log
   panel for errors.

Every later `git push` to `main` redeploys the app automatically.

### Make it viewable without signing in

**Apps from a private GitHub repo are private by default**, so visitors are sent to a Streamlit
login page. For a portfolio link, open the app, click **Share** (top right), then **Make this
app public**. Or go to **App settings → Sharing → Who can view this app → "This app is public
and searchable"**.

This only changes who can *use* the app; the code stays private. Community Cloud allows one
private app at a time.

To check, open the URL in a private/incognito window. You should see the app, not a login page.
From a terminal, `curl -sI https://retpulse.streamlit.app/` should **not** redirect to `/-/login`.

**Optional: make the repo public too**, so reviewers can read the code and see the CI badge
(GitHub → repo **Settings → General → Danger Zone → Change visibility**). Commits carry their
author name and email, which become visible once the repo is public. To use GitHub's private
`noreply` address for future commits, see GitHub's *email settings* page.

## Step 3: check the live app

Use the sample data, so the expected numbers are known:

- [ ] The app opens on the **welcome page** (logo, gradient, no sidebar). **Privacy Policy** and
      **Terms of Use** open as dialogs. Check it on a phone too.
- [ ] **Review Your CSV** opens **Overview** with the "Load your data" panel (sales and products
      columns, plus a **Use sample data** button), and the sidebar shows the RetailPulse logo.
- [ ] **Use sample data** shows: net revenue **219,863.42**, gross profit **96,437.50**, margin
      **45.2%**, orders **5,740**, average order value **38.81**.
- [ ] The trend chart peaks in December. Hovering shows a tooltip.
- [ ] **Products** shows the top 10 with Espresso Roast and House Blend first.
- [ ] **Inventory** shows dead stock (Barista Apron, Gingerbread Cookies) and one product out of stock.
- [ ] **Recommendations** shows 6 cards: 1 below cost, 2 reorder, 2 clearance, 1 low margin.
- [ ] **Data quality** shows 9,166 sales lines ready, 22 rejected rows, and a download button for them.
- [ ] Sidebar: "Last 30 days" changes the KPIs and shows change arrows; lowering "Low cover" to 1
      removes the reorder cards.
- [ ] Upload your own file: try `tests/fixtures/golden/sales.csv` and `products.csv`. Net revenue
      should be **1,838.00**.
- [ ] Switch the theme (⋮ menu → Settings → Dark). Charts change to the dark palette and stay
      readable.
- [ ] Each CSV download opens correctly in Excel.

## Step 4: finish the portfolio touches

- Add the live URL to the top of `README.md` (replace the "Live demo" placeholder) and to the
  GitHub repo's **About → Website** field.
- Add a screenshot or GIF of the Overview page to the README.

## Day-to-day behaviour

- **Sleep:** an app with no traffic for 12 hours goes to sleep. The next visitor sees a "wake up"
  button, and the app takes about 30 seconds to start. Visiting the app before an interview keeps
  it awake.
- **Updates:** pushing to `main` redeploys. Community Cloud allows at most five updates per minute
  from GitHub.
- **Welcome page:** every new session (including a page refresh) starts on the welcome page.
- **Python version:** you can't change it in place. Delete the app, then redeploy with the same
  subdomain and the new version (Advanced settings).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Build fails while installing packages | Check the log. Make sure `requirements.txt` wasn't changed to something without Linux wheels, then run the `pip download` check above. |
| `ModuleNotFoundError: retailpulse` or `ui` | The main file path must be `streamlit_app.py` at the repo root. |
| "You've hit the resource limits" | Too much memory, usually several large uploads at once. Reboot the app from **Manage app**. Consider lowering `maxUploadSize`. |
| Sample data button shows an error | `data/sample/` must be committed. Check that `git ls-files data/sample` lists both CSVs. |
| Every uploaded row is rejected as "in the future" | The server's clock is behind the data. This is very unlikely on Community Cloud; check the dates in the file. |
