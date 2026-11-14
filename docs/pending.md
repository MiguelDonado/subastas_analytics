Dashboard features

1. Popups. Your todo already notes a conflict: clicking a red marker currently deselects the lot. With popups, one click would deselect and open a popup at the same time. The red markers would also need their own popup, because they cover the blue ones. Decide on that behaviour before building.
2. Cluster points. clusterOptions = markerClusterOptions() on addCircleMarkers. Check that clicking a marker, highlighting and zooming still work when the lot's markers are inside a cluster.
3. Lot reviews (interested / maybe / discarded + notes), plus the Status filter. The design is already in docs/3.app_design.md (app.lot_reviews). On login:
   - If you're the only person marking lots, you don't need a full user system. You do need a gate, though: once the app is public on Connect Cloud, anyone with the URL could change your marks. Options:
     - Make the app private on Connect Cloud. I'm not sure the free plan allows that, so check.
     - A single password, stored as an env var, that unlocks editing.
     - shinymanager, a simple login screen.
   - You only need real logins if several people will keep their own marks. In that case lot_reviews also needs a user_id column.
   - This is the first time the app writes to the DB. If you planned a read-only DB user for the app, it now needs write access to the app schema.

Deployment (Neon + Posit Connect Cloud)

- Move the data to Neon (dump and restore subastas-db) and point Airflow's connection at Neon instead of the local container.
- Data goes stale: app.R reads gold.app_lots and the references once, at the top level, when the app starts. On Connect Cloud a running app won't see what Airflow loads until it restarts. To fix it, read the data inside the server function (once per session), or use reactivePoll.
- Secrets: add the SUBASTAS_DB_* vars in Connect Cloud's settings, since your .Renviron isn't deployed. Make sure renv.lock is up to date and the deploy is set to use it.
- Neon cold starts: the free tier suspends the DB when it's idle, so the first load may be slow. That's fine, but worth knowing.

From docs/todo.md, easy to forget

- Rotate the Goolzoom API key. It was pasted in plain text into a session, so do this first, whatever else you pick.
- Extra map layers. Your todo lists Hidrografía, 3D (Google Maps), Catastro transparente and IGN. Hidrografía and the Catastro parcels are already planned in the app design. Google Maps can't be used, because loading its tiles directly breaks Google's terms (noted in the app design).
- Write down what dashboard/.Renviron and dashboard/.env are each for. Both exist right now, which is confusing.
- Note the visorSIU link for land classification.
- Nice to have: e2e tests, and switching to an open-source LLM to cut costs.

My suggested order:
1. Rotate the key.
2. Clusters (quick).
3. Popups (settle the click behaviour first).
4. Reviews with a simple password gate.
5. Deploy, fixing the stale-data issue as part of it.