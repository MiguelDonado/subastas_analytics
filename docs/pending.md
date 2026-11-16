Deployment (Neon + Posit Connect Cloud)

- Data goes stale: app.R reads gold.app_lots and the references once, at the top level, when the app starts. On Connect Cloud a running app won't see what Airflow loads until it restarts. To fix it, read the data inside the server function (once per session), or use reactivePoll.
- Secrets: add the SUBASTAS_DB_* vars in Connect Cloud's settings, since your .Renviron isn't deployed. Make sure renv.lock is up to date and the deploy is set to use it.
- Neon cold starts: the free tier suspends the DB when it's idle, so the first load may be slow. That's fine, but worth knowing.

From docs/todo.md, easy to forget

- Extra map layers. Your todo lists Hidrografía, 3D (Google Maps), Catastro transparente and IGN. Hidrografía and the Catastro parcels are already planned in the app design. Google Maps can't be used, because loading its tiles directly breaks Google's terms (noted in the app design).
- Nice to have: e2e tests, and switching to an open-source LLM to cut costs.

My suggested order:
1. Reviews with a simple password gate.
2. Deploy, fixing the stale-data issue as part of it.