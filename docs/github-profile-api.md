# Dynamic GitHub Profile Cards

The profile README embeds SVG cards served by the owner's VPS. The cards are rendered on demand from GitHub's official APIs; generated repository names and statistics are no longer written into README.md.

## Public endpoints

Base URL: https://theloi.io.vn/dev/github-profile.php

| Endpoint | Output |
| --- | --- |
| ?type=stats | Public repository count, followers, following, stars and forks |
| ?type=repositories&sort=stars | Six most-starred eligible public repositories |
| ?type=repositories&sort=updated | Six recently pushed eligible public repositories |
| ?type=repositories&sort=random | Six rotating picks from the 15 most-starred eligible repositories |
| ?type=languages | Language byte distribution across up to 20 top non-fork public repositories |
| ?type=contributions | Full contribution calendar when GraphQL auth is configured; otherwise recent public activity |

All endpoints return image/svg+xml and accept GET requests only.

## Data sources

- GitHub REST GET /users/{username} for account-level public metrics.
- GitHub REST GET /users/{username}/repos for public repositories and metadata.
- GitHub REST GET /repos/{owner}/{repo}/languages for language byte counts.
- GitHub REST GET /users/{username}/events/public for the recent public activity fallback.
- GitHub GraphQL user.contributionsCollection.contributionCalendar for the official contribution calendar.

## Cache policy

- Profile and repository metadata: 15 minutes.
- Contribution calendar / public activity: 6 hours.
- Language aggregation: 24 hours.
- SVG HTTP cache: 5 minutes with stale-while-revalidate.
- If GitHub is temporarily unavailable, a previously cached response may be served for up to seven days.

The server-side cache is stored under the operating system temporary directory with restricted permissions. No repository data is written back into README.md.

## Full contribution calendar (optional)

The full 12-month contribution calendar requires a GitHub personal access token that can read the authenticated user's profile (read:user for a classic token).

Set the token as the PHP runtime environment variable: GITHUB_PROFILE_TOKEN.

Do not commit the token to this repository, place it in a public README, or include it in a URL. The endpoint reads the variable server-side and never returns it. If the variable is absent or GraphQL is unavailable, the card falls back to recent public events and labels that data accordingly.

## README embedding

The repository image is wrapped in a link to https://github.com/lowji194?tab=repositories because links inside an SVG displayed as an image are not individually clickable in GitHub README. The statistics, contribution and language cards are standalone images.

GitHub may cache proxied README images independently of the VPS cache. A change in GitHub data can therefore take a little longer to appear in the rendered profile.