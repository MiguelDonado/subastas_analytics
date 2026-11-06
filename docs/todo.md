Capas for shiny application: Hidrografia, 3D (Google Maps), Catastro transparente, IGN
rotate api key goolzoom, because i paste it unintentionaly in plain text in claude session






- I guess once I make sure all the edge cases are handled, then i can just lower from 7 days, and add a bit of redundancy, and that would not be a problem cuz i already handled that redundant things dont cause problems in the edge cases.
- **Failed days:** one bad day fails the whole week's run, and a retry repeats all 7 days.

- I think it should look not only 7 days before in the dag timedelta, but 14 days before for redundancy, because dag runs once per week, and imaging one week doesnt run, if only looks 7 days behind i would lose data.

workflow diagram

quality checks

logs very well


# Improvements
- [] Use systemd timer instead of cron. It has the advantage that if computer is off, it would trigger the script whenever computer starts, whereas cron doesnt. If computer off, during cron schedule, cron job would not be executed.
  - Biggest differences:
    1. Persistent timers (recover missed executions)
    2. Monotonic timers (schedule jobs relative to system events, example 5 minutes after booting PC)
    3. Resource management (control the resources that a given job uses, so that it doesnt end up taking a lot of memory...)
    4. Centralized logging with journald
    5. Dependency management (imaging you have a backup service for a db, but it needs the database service to be running first, so with cron we would have to implement those checks manually on the script, whereas with systemd it can be easily implemented by declaring relationships between services.)