FROM astrocrpublic.azurecr.io/runtime:3.3-11

# Install the subastas_analytics package so DAGs can `import subastas_analytics`.
#
# By the time this line runs, the base image's ONBUILD steps have already copied
# the project into /usr/local/airflow (minus .dockerignore). `pip install <folder>`
# reads pyproject.toml there, builds the package from src/ and installs it with
# its dependencies (python-dotenv, ...), so pyproject.toml is the
# single source of truth: `uv add` a dependency and the next build picks it up.
# Packages already in the image that satisfy our requirements (e.g. requests) are
# left alone, so Airflow's own versions don't change.
#
# src/ is NOT mounted into the containers: after changing code in src/ or
# pyproject.toml, rebuild with `astro dev restart`.
RUN pip install --no-cache-dir /usr/local/airflow