Capas for shiny application: Hidrografia, 3D (Google Maps), Catastro transparente, IGN
rotate api key goolzoom, because i paste it unintentionaly in plain text in claude session

workflow diagram

quality checks



# Improvements
- [] Use systemd timer instead of cron. It has the advantage that if computer is off, it would trigger the script whenever computer starts, whereas cron doesnt. If computer off, during cron schedule, cron job would not be executed.
  - Biggest differences:
    1. Persistent timers (recover missed executions)
    2. Monotonic timers (schedule jobs relative to system events, example 5 minutes after booting PC)
    3. Resource management (control the resources that a given job uses, so that it doesnt end up taking a lot of memory...)
    4. Centralized logging with journald
    5. Dependency management (imaging you have a backup service for a db, but it needs the database service to be running first, so with cron we would have to implement those checks manually on the script, whereas with systemd it can be easily implemented by declaring relationships between services.)