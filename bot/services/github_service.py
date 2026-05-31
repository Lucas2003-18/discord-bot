import logging
from datetime import datetime, timedelta, timezone
from github import Github, GithubException
from bot import config

log = logging.getLogger(__name__)


def get_recent_activity() -> dict | None:
    try:
        gh = Github(config.GITHUB_TOKEN)
        user = gh.get_user(config.GITHUB_USERNAME)
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        commits = []
        prs = []

        for repo in user.get_repos(type="owner", sort="updated"):
            if repo.updated_at < since:
                break
            try:
                for commit in repo.get_commits(since=since, author=config.GITHUB_USERNAME):
                    commits.append({
                        "repo": repo.name,
                        "message": commit.commit.message.splitlines()[0],
                        "url": commit.html_url,
                    })
            except GithubException:
                pass

        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        for issue in gh.search_issues(f"type:pr author:{config.GITHUB_USERNAME} updated:>={since_str}"):
            prs.append({
                "repo": issue.repository.name if issue.repository else "?",
                "title": issue.title,
                "state": issue.state,
                "url": issue.html_url,
            })
            if len(prs) >= 5:
                break

        return {"commits": commits[:10], "prs": prs[:5]}
    except Exception as e:
        log.error("github_service error: %s", e)
        return None
